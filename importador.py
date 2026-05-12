# Importa o pandas para manipulação e estruturação dos dados
import pandas as pd
# Importa o create_engine para gerenciar a conexão e inspect para inspecionar o banco SQLite
from sqlalchemy import create_engine, inspect
# Importa a biblioteca nativa tkinter, responsável por renderizar a janela de seleção do Windows
import tkinter as tk
# Importa especificamente o submódulo filedialog para abrir a caixa de 'Abrir Arquivo'
from tkinter import filedialog
# Importa a biblioteca os para interações com o sistema operacional
import os
import csv
import re
import unicodedata

# Define a conexão direta com o banco de dados que criamos
engine = create_engine('sqlite:///gerel_produtividade.db', connect_args={"timeout": 30})

def escapar_identificador_sql(nome):
    return '"' + nome.replace('"', '""') + '"'

def contar_registros(nome_tabela):
    from sqlalchemy import text
    tabela_sql = escapar_identificador_sql(nome_tabela)
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {tabela_sql}")).scalar_one()

def limpar_valores_nulos(df):
    total_nulos = int(df.isna().sum().sum())
    df = df.fillna('')
    df = df.replace(
        to_replace=r'^\s*(NULL|NULO|NONE|NAN|NAT)\s*$',
        value='',
        regex=True
    )
    df = df.astype(str)
    df = df.replace(
        to_replace=r'^\s*(NULL|NULO|NONE|NAN|NAT|<NA>)\s*$',
        value='',
        regex=True
    )
    if total_nulos > 0:
        print(f"[LIMPEZA] {total_nulos:,} valores nulos substituidos por texto vazio antes da importacao.")
    return df

def normalizar_nome_coluna(nome):
    texto = str(nome).replace('\ufeff', '').replace('\xa0', ' ').strip()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', '', texto.lower())

def aplicar_mapeamento_colunas(df, mapeamento):
    df = df.copy()
    df.columns = [str(coluna).replace('\ufeff', '').replace('\xa0', ' ').strip() for coluna in df.columns]

    aliases = {}
    for origem, destino in mapeamento.items():
        aliases[normalizar_nome_coluna(origem)] = destino
        aliases[normalizar_nome_coluna(destino)] = destino

    renomear = {}
    for coluna in df.columns:
        destino = mapeamento.get(coluna) or aliases.get(normalizar_nome_coluna(coluna))
        if destino:
            renomear[coluna] = destino

    df = df.rename(columns=renomear)
    if df.columns.duplicated().any():
        duplicadas = sorted(set(df.columns[df.columns.duplicated()].tolist()))
        print(f"[LIMPEZA] Colunas duplicadas apos padronizacao ignoradas: {', '.join(duplicadas)}.")
        df = df.loc[:, ~df.columns.duplicated()]
    return df

def extrair_codigo_atendimento(valor):
    texto = str(valor).strip()
    match = re.search(r'\d+', texto)
    return match.group(0) if match else texto

def tornar_colunas_unicas(colunas):
    contagem = {}
    resultado = []
    for coluna in colunas:
        nome = str(coluna).replace('\ufeff', '').replace('\xa0', ' ').strip()
        repeticao = contagem.get(nome, 0)
        resultado.append(nome if repeticao == 0 else f"{nome}.{repeticao}")
        contagem[nome] = repeticao + 1
    return resultado

def ajustar_campos_csv(campos, total_colunas, indice_email=None):
    if len(campos) > total_colunas:
        excesso = len(campos) - total_colunas
        if indice_email is not None and excesso > 1 and len(campos) > indice_email + excesso:
            campos = (
                campos[:indice_email]
                + [';'.join(campos[indice_email:indice_email + excesso])]
                + campos[indice_email + excesso:]
            )
        if len(campos) > total_colunas:
            campos = campos[:total_colunas]
    elif len(campos) < total_colunas:
        campos = campos + [''] * (total_colunas - len(campos))
    return campos

def destinos_mapeados(colunas, mapeamento):
    aliases = {}
    for origem, destino in mapeamento.items():
        aliases[normalizar_nome_coluna(origem)] = destino
        aliases[normalizar_nome_coluna(destino)] = destino
    return [aliases.get(normalizar_nome_coluna(coluna)) for coluna in colunas]

def ajustar_cabecalho_se_necessario(df, mapeamento, pk_banco):
    if pk_banco in destinos_mapeados(df.columns, mapeamento):
        return df

    aliases = destinos_mapeados
    limite = min(len(df), 25)
    for indice in range(limite):
        valores_linha = df.iloc[indice].tolist()
        destinos = aliases(valores_linha, mapeamento)
        total_colunas_conhecidas = sum(1 for destino in destinos if destino)
        if pk_banco in destinos or total_colunas_conhecidas >= 3:
            novo_df = df.iloc[indice + 1:].copy()
            novo_df.columns = [str(valor).replace('\ufeff', '').replace('\xa0', ' ').strip() for valor in valores_linha]
            novo_df = novo_df.loc[:, [normalizar_nome_coluna(coluna) != '' for coluna in novo_df.columns]]
            print(f"[INFO] Cabecalho detectado na linha {indice + 1} do arquivo.")
            return novo_df
    return df

def ler_csv_dados(caminho_arquivo, codigos_atendimento=None):
    with open(caminho_arquivo, 'r', encoding='latin1', errors='replace') as arquivo:
        primeiras_linhas = [arquivo.readline() for _ in range(50)]

    melhor_separador = ';'
    melhor_linha = 0
    melhor_total_colunas = 1
    cabecalho_encontrado = False

    # Colunas-chave de qualquer tabela do sistema — quando encontradas, a linha é o cabeçalho
    COLUNAS_CHAVE = {'protocoloid', 'noatendimento', 'mat', 'protocolo'}

    for separador in [';', ',', '\t']:
        for indice, linha in enumerate(primeiras_linhas):
            if not linha:
                continue
            campos = linha.rstrip('\r\n').split(separador)
            nomes_normalizados = {normalizar_nome_coluna(campo) for campo in campos}

            # Se a linha contiver qualquer coluna-chave conhecida, é o cabeçalho real
            if COLUNAS_CHAVE.intersection(nomes_normalizados):
                melhor_separador = separador
                melhor_linha = indice
                melhor_total_colunas = len(campos)
                cabecalho_encontrado = True
                break

            total_colunas = len(campos)
            if total_colunas > melhor_total_colunas:
                melhor_separador = separador
                melhor_linha = indice
                melhor_total_colunas = total_colunas
        if cabecalho_encontrado:
            break

    with open(caminho_arquivo, 'r', encoding='latin1', errors='replace', newline='') as arquivo:
        leitor = csv.reader(arquivo, delimiter=melhor_separador)
        for _ in range(melhor_linha):
            next(leitor, None)
        cabecalho = next(leitor, [])
        colunas = tornar_colunas_unicas(cabecalho)
        total_colunas = len(colunas)
        indice_email = next((i for i, coluna in enumerate(cabecalho) if normalizar_nome_coluna(coluna) == 'email'), None)
        indice_tipo_atendimento = next(
            (i for i, coluna in enumerate(cabecalho) if normalizar_nome_coluna(coluna) == 'tipoatendimento'),
            None
        )
        linhas = []
        linhas_ajustadas = 0
        linhas_lidas = 0
        linhas_pre_filtradas = 0
        for campos in leitor:
            if not campos or all(str(campo).strip() == '' for campo in campos):
                continue
            linhas_lidas += 1
            if codigos_atendimento and indice_tipo_atendimento is not None and indice_tipo_atendimento < len(campos):
                codigo = extrair_codigo_atendimento(campos[indice_tipo_atendimento])
                if codigo not in codigos_atendimento:
                    linhas_pre_filtradas += 1
                    continue
            tamanho_original = len(campos)
            if len(campos) != total_colunas:
                campos = ajustar_campos_csv(campos, total_colunas, indice_email)
                if tamanho_original != len(campos):
                    linhas_ajustadas += 1
            linhas.append(campos)

    df = pd.DataFrame(linhas, columns=colunas)

    if melhor_linha > 0:
        print(f"[INFO] Cabecalho CSV detectado na linha {melhor_linha + 1}.")
    if melhor_separador != ';':
        print(f"[INFO] CSV lido usando separador alternativo: {repr(melhor_separador)}")
    if codigos_atendimento and linhas_pre_filtradas:
        print(f"[FILTRO] Pre-filtro CSV: {linhas_lidas:,} registros lidos -> {len(linhas):,} registros com tipo permitido.")
    if linhas_ajustadas:
        print(f"[LIMPEZA] {linhas_ajustadas:,} linha(s) CSV com quantidade de campos ajustada.")
    return df

def concatenar_abas_excel(abas):
    partes = [df for df in abas.values() if not df.empty]
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)

def ler_html_dados(caminho_arquivo):
    tabelas = pd.read_html(caminho_arquivo, encoding='latin1')
    partes = [df for df in tabelas if not df.empty]
    if not partes:
        return pd.DataFrame()
    print("[INFO] Arquivo HTML/XLS lido como tabela HTML.")
    return pd.concat(partes, ignore_index=True)

def ler_arquivo_dados(caminho_arquivo, codigos_atendimento=None):
    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    extensoes_excel = {'.xlsx', '.xlsm', '.xlsb', '.xls'}

    if extensao in {'.html', '.htm'}:
        return ler_html_dados(caminho_arquivo)

    if extensao in extensoes_excel:
        try:
            opcoes = {'sheet_name': None, 'dtype': str}
            if extensao == '.xlsb':
                opcoes['engine'] = 'pyxlsb'
            abas = pd.read_excel(caminho_arquivo, **opcoes)
            print(f"[INFO] Arquivo Excel lido: {extensao}")
            return concatenar_abas_excel(abas)
        except Exception as erro_excel:
            print(f"[AVISO] Falha ao ler como Excel ({extensao}): {erro_excel}")
            if extensao == '.xls':
                try:
                    return ler_html_dados(caminho_arquivo)
                except Exception as erro_html:
                    print(f"[AVISO] Falha ao ler XLS como HTML: {erro_html}")

    return ler_csv_dados(caminho_arquivo, codigos_atendimento=codigos_atendimento)

def preparar_colunas_para_banco(df, colunas_banco):
    colunas_faltantes = [col for col in colunas_banco if col not in df.columns]
    for coluna in colunas_faltantes:
        df[coluna] = ''
    if colunas_faltantes:
        print(f"[LIMPEZA] {len(colunas_faltantes):,} colunas ausentes no arquivo preenchidas com texto vazio.")
    return df[colunas_banco]

def validar_chave_primaria(df, nome_tabela, pk_banco):
    if pk_banco in df.columns:
        return True

    colunas_arquivo = ", ".join(df.columns[:8])
    print(f"\n[ERRO] O arquivo selecionado nao possui a chave primaria '{pk_banco}' da tabela '{nome_tabela}'.")
    print("[ERRO] A importacao foi cancelada para evitar registros sem identificador ou na tabela errada.")
    print(f"[INFO] Primeiras colunas encontradas no arquivo: {colunas_arquivo}")

    if nome_tabela == 'relatorio_ocorrencias' and 'No.Atendimento' in df.columns:
        print("[DICA] Esse arquivo parece ser de SAPS. Selecione a tabela 'saps_atendimentos'.")
    return False

def limpar_nulls_no_banco(nome_tabela):
    from sqlalchemy import text

    tabela_sql = escapar_identificador_sql(nome_tabela)
    inspetor = inspect(engine)
    colunas = [coluna['name'] for coluna in inspetor.get_columns(nome_tabela)]

    total_nulls = 0
    with engine.begin() as conn:
        for coluna in colunas:
            coluna_sql = escapar_identificador_sql(coluna)
            qtd_coluna = conn.execute(
                text(f"SELECT COUNT(*) FROM {tabela_sql} WHERE {coluna_sql} IS NULL")
            ).scalar_one()
            if qtd_coluna:
                conn.execute(text(f"UPDATE {tabela_sql} SET {coluna_sql} = '' WHERE {coluna_sql} IS NULL"))
                total_nulls += qtd_coluna

    if total_nulls > 0:
        print(f"[LIMPEZA] {total_nulls:,} valores NULL ja existentes foram corrigidos na tabela '{nome_tabela}'.")

def atualizar_registros_existentes(df_existente, nome_tabela, pk_banco):
    from sqlalchemy import text

    if df_existente.empty:
        return 0

    tabela_sql = escapar_identificador_sql(nome_tabela)
    colunas_atualizacao = [col for col in df_existente.columns if col != pk_banco]
    if not colunas_atualizacao:
        return 0

    set_sql = ", ".join(
        f"{escapar_identificador_sql(coluna)} = :{coluna}"
        for coluna in colunas_atualizacao
    )
    pk_sql = escapar_identificador_sql(pk_banco)
    sql = text(f"UPDATE {tabela_sql} SET {set_sql} WHERE {pk_sql} = :{pk_banco}")

    registros = df_existente.to_dict(orient='records')
    with engine.begin() as conn:
        conn.execute(sql, registros)

    return len(registros)

# Cria um dicionário de configuração centralizado. Ele guarda a Chave Primária (pk) e o mapeamento de colunas de cada tabela
CONFIG_TABELAS = {
    'controle_pessoa': {
        'pk': 'MAT',
        'map': {
            'MAT.': 'MAT', 'DATA DE NASCIMENTO': 'DATA_DE_NASCIMENTO', 'DESLIGAMENTO\nDATA': 'DATA_DESLIGAMENTO',
            'COORDENADOR/SUPERVISOR/GERENTE': 'COORDENADOR_SUPERVISOR_GERENTE',
            'COORDENADOR/GERENTE/DIRETOR': 'COORDENADOR_GERENTE_DIRETOR',
            'HORARIO DE ENTRADA': 'HORARIO_DE_ENTRADA', 'HORARIO DE SAÍDA': 'HORARIO_DE_SAIDA',
            'DATA DA ADMISSAO': 'DATA_DA_ADMISSAO', 'DATA DE EFETIVACAO': 'DATA_DE_EFETIVACAO',
            'CARGA HORARIA': 'CARGA_HORARIA', 'EMAIL DA EMPRESA': 'EMAIL_DA_EMPRESA',
            'TEMPO DE CASA': 'TEMPO_DE_CASA', 'PERFIL - INTERACT': 'PERFIL_INTERACT',
            'ENDERECO COMPLETO': 'ENDERECO_COMPLETO', 'TELEFONE RESIDENCIAL': 'TELEFONE_RESIDENCIAL',
            'TELEFONE CELULAR': 'TELEFONE_CELULAR', 'INICIO': 'INICIO_1', 'FIM': 'FIM_1',
            'INICIO.1': 'INICIO_2', 'RETORNO': 'RETORNO_1', 'INICIO.2': 'INICIO_3',
            'RETORNO.1': 'RETORNO_2', 'TIPO DE TO': 'TIPO_DE_TO', 'EASY CALL': 'EASY_CALL',
            'PORTAL DO CONHECIMENTO / SAPS/ DESKTOP': 'PORTAL_SAPS_DESKTOP',
            'OS (CANCELAMENTO)': 'OS_CANCELAMENTO', 'MAT ANTERIOR': 'MAT_ANTERIOR',
            'DATA DA ALTERACAO': 'DATA_DA_ALTERACAO', 'PREVISAO RETORNO ': 'PREVISAO_RETORNO',
            'INICIO.3': 'INICIO_4', 'PREVISAO': 'PREVISAO_1', 'RETORNO.2': 'RETORNO_3',
            'INICIO.4': 'INICIO_5', 'RETORNO.3': 'RETORNO_4', 'INICIO.5': 'INICIO_6',
            'RETORNO.4': 'RETORNO_5', 'GERĘNCIAS': 'GERENCIAS',
            'INÍCIO DE TREINAMENTO': 'INICIO_TREINAMENTO', 'UNIDADE DE ORIGEM': 'UNIDADE_DE_ORIGEM'
        }
    },
    'relatorio_ocorrencias': {
        'pk': 'Protocolo_ID',
        'map': {
            'Nome do Beneficiario':      'Nome_Beneficiario',
            'Tipo de Atendimento':       'Tipo_Atendimento',
            'Tipo Macro':                'Tipo_Macro',
            'Tipo Ocorrencia':           'Tipo_Ocorrencia',
            'Prioridade':                'Prioridade',
            'Data de Entrada':           'Data_Entrada',
            'Hora de Entrada':           'Hora_Entrada',
            'Data Final':                'Data_Final',
            'Hora Final':                'Hora_Final',
            'Qde NIP':                   'Qde_NIP',
            'Qde Liminar':               'Qde_Liminar',
            'Qde Prioridade':            'Qde_Prioridade',
            'Tipo de Prazo':             'Tipo_Prazo',
            'Prazo Planejado':           'Prazo_Planejado',
            'Prazo Real':                'Prazo_Real',
            'SLA da Ficha':              'SLA_da_Ficha',
            'Num Etapa':                 'Num_Etapa',
            'Usuario Mov.':              'Usuario_Mov',
            'Setor Usuário Mov.':        'Setor_Usuario_Mov',
            'Setor Usu\udce1rio Mov.':   'Setor_Usuario_Mov',
            'Subsetor Usuário Mov.':     'Subsetor_Usuario_Mov',
            'Subsetor Usu\udce1rio Mov.':'Subsetor_Usuario_Mov',
            'Data Início Etapa':         'Data_Inicio_Etapa',
            'Data In\udcedcio Etapa':    'Data_Inicio_Etapa',
            'Hora Início Etapa':         'Hora_Inicio_Etapa',
            'Hora In\udcedcio Etapa':    'Hora_Inicio_Etapa',
            'Data Final Etapa':          'Data_Final_Etapa',
            'Hora Final Etapa':          'Hora_Final_Etapa',
            'Status da Etapa':           'Status_da_Etapa',
            'Prazo Planejado Etapa':     'Prazo_Planejado_Etapa',
            'Prazo Real Etapa':          'Prazo_Real_Etapa',
            'SLA Etapa':                 'SLA_Etapa',
        }
    },
    'saps_atendimentos': {
        'pk': 'No_Atendimento',
        'map': {
            'Tipo Atendimento': 'Tipo_Atendimento',
            'Tipo de Atendimento': 'Tipo_Atendimento',
            'No.Atendimento': 'No_Atendimento',
            'No Atendimento': 'No_Atendimento',
            'Nº Atendimento': 'No_Atendimento',
            'N° Atendimento': 'No_Atendimento',
            'Numero Atendimento': 'No_Atendimento',
            'Número Atendimento': 'No_Atendimento',
            'Data de entrada': 'Data_Entrada',
            'Matrícula': 'Matricula',
            'MatrÃ­cula': 'Matricula',
            'Data da proposta': 'Data_Da_Proposta',
            'Endereço': 'Endereco',
            'EndereÃ§o': 'Endereco',
            'Data de fechamento': 'Data_De_Fechamento',
            'Operador Final': 'Operador_Final',
            'Sub Motivos': 'Sub_Motivos',
            'Médico|Funcionário': 'Medico_Funcionario',
            'MÃ©dico|FuncionÃ¡rio': 'Medico_Funcionario',
            'Crítico': 'Critico',
            'CrÃ­tico': 'Critico',
            'Caso/Crítico': 'Caso_Critico',
            'Caso/CrÃ­tico': 'Caso_Critico',
            'Follow up': 'Follow_Up',
            'Follow up/Motivo': 'Follow_Up_Motivo',
            'Reclamação': 'Reclamacao',
            'ReclamaÃ§Ã£o': 'Reclamacao',
            'Código do Solicitante': 'Codigo_Do_Solicitante',
            'CÃ³digo do Solicitante': 'Codigo_Do_Solicitante',
            'Código do Grupo': 'Codigo_Do_Grupo_1',
            'CÃ³digo do Grupo': 'Codigo_Do_Grupo_1',
            'Código do Executor': 'Codigo_Do_Executor',
            'CÃ³digo do Executor': 'Codigo_Do_Executor',
            'Código do Grupo.1': 'Codigo_Do_Grupo_2',
            'CÃ³digo do Grupo.1': 'Codigo_Do_Grupo_2',
            'Grupo': 'Grupo_1',
            'Grupo.1': 'Grupo_2',
            'Diagnóstico': 'Diagnostico',
            'DiagnÃ³stico': 'Diagnostico',
            'TUSS Inicial': 'TUSS_Inicial'
        }
    }
}

# Função mestre de ETL adaptada para receber dinamicamente qualquer arquivo baseado na escolha do usuário
def executar_etl(caminho_arquivo, nome_tabela, pk_banco, mapeamento):
    # Verifica dinamicamente se a extensão do arquivo selecionado é Excel
    is_excel = True
    
    # Tenta realizar a leitura do arquivo dependendo do seu formato estrutural
    if is_excel:
        # Lê todas as abas do Excel e as concatena ignorando o índice original
        try:
            cfg_filtro_previo = CONFIG_TABELAS[nome_tabela].get('filtro')
            codigos_atendimento = cfg_filtro_previo['codigos'] if cfg_filtro_previo else None
            df = ler_arquivo_dados(caminho_arquivo, codigos_atendimento=codigos_atendimento)
        except Exception as e:
            print(f"[ERRO] Falha ao ler o arquivo: {e}")
            return False
    else:
        # Bloco de tentativa para ler o CSV garantindo a codificação correta para acentos (latin1)
        try:
            df = ler_csv_dados(caminho_arquivo)
        # Captura eventuais erros de leitura e avisa o usuário sem quebrar o programa
        except Exception as e:
            print(f"[ERRO] Falha ao ler o CSV: {e}")
            return False
    
    # Executa a renomeação das colunas 'sujas' do arquivo para as colunas 'limpas' do banco
    df = ajustar_cabecalho_se_necessario(df, mapeamento, pk_banco)
    df = aplicar_mapeamento_colunas(df, mapeamento)

    if not validar_chave_primaria(df, nome_tabela, pk_banco):
        return False

    # Remove linhas onde a Chave Primária é nula (linhas vazias ou de rodapé do arquivo)
    if pk_banco in df.columns:
        total_bruto = len(df)
        cabecalhos_repetidos = df[pk_banco].map(normalizar_nome_coluna) == normalizar_nome_coluna(pk_banco)
        if cabecalhos_repetidos.any():
            df = df[~cabecalhos_repetidos]
            print(f"[LIMPEZA] {int(cabecalhos_repetidos.sum()):,} linha(s) de cabecalho repetido removidas.")
        df = df[df[pk_banco].notna() & (df[pk_banco].astype(str).str.strip() != '')]
        removidos_pk = total_bruto - len(df)
        if removidos_pk > 0:
            print(f"[LIMPEZA] {removidos_pk:,} linhas sem Chave Primaria ('{pk_banco}') descartadas.")

        duplicados = df.duplicated(subset=[pk_banco], keep='last')
        total_duplicados = int(duplicados.sum())
        if total_duplicados > 0:
            df = df[~duplicados]
            print(f"[LIMPEZA] {total_duplicados:,} linhas duplicadas no arquivo foram ignoradas pela chave '{pk_banco}'.")

    # Aplica filtro de tipos permitidos, se configurado para esta tabela
    cfg_filtro = CONFIG_TABELAS[nome_tabela].get('filtro')
    if cfg_filtro:
        col_filtro = cfg_filtro['coluna']
        codigos_validos = cfg_filtro['codigos']
        if col_filtro in df.columns:
            total_antes = len(df)
            # Remove explicitamente nulos antes do filtro para evitar que NaN vire a string 'nan'
            df = df[df[col_filtro].notna() & (df[col_filtro].astype(str).str.strip() != '')]
            # Extrai o código numérico antes do '-' e verifica se está na lista permitida
            codigos_arquivo = df[col_filtro].map(extrair_codigo_atendimento)
            df = df[codigos_arquivo.isin(codigos_validos)]
            print(f"[FILTRO] {total_antes:,} registros lidos -> {len(df):,} registros apos filtro de tipo de atendimento.")
            if df.empty:
                amostra_codigos = sorted(set(codigos_arquivo.dropna().astype(str).head(10).tolist()))
                print("[AVISO] Nenhum registro passou no filtro de tipo de atendimento.")
                if amostra_codigos:
                    print(f"[INFO] Primeiros codigos encontrados no arquivo: {', '.join(amostra_codigos)}")
                return False
        else:
            print(f"[AVISO] Coluna de filtro '{col_filtro}' nao encontrada no arquivo. Nenhum filtro aplicado.")

    # Inicia o inspetor do SQLAlchemy para verificar a estrutura real do banco de dados
    inspetor = inspect(engine)
    # Extrai uma lista exata de quais colunas existem atualmente na tabela selecionada
    colunas_banco = [coluna['name'] for coluna in inspetor.get_columns(nome_tabela)]
    
    # Realiza um filtro agressivo: mantém no DataFrame apenas as colunas que têm correspondência exata no banco
    df = df[[col for col in df.columns if col in colunas_banco]]
    df = preparar_colunas_para_banco(df, colunas_banco)
    df = limpar_valores_nulos(df)

    total_antes_pk_limpa = len(df)
    df = df[df[pk_banco].astype(str).str.strip() != '']
    removidos_pk_limpa = total_antes_pk_limpa - len(df)
    if removidos_pk_limpa > 0:
        print(f"[LIMPEZA] {removidos_pk_limpa:,} linhas sem Chave Primaria ('{pk_banco}') descartadas apos limpeza.")

    duplicados = df.duplicated(subset=[pk_banco], keep='last')
    total_duplicados = int(duplicados.sum())
    if total_duplicados > 0:
        df = df[~duplicados]
        print(f"[LIMPEZA] {total_duplicados:,} linhas duplicadas no arquivo foram ignoradas pela chave '{pk_banco}'.")

    # Bloco para consultar as chaves primárias que já existem cadastradas no banco de dados
    try:
        # Faz um SELECT focado exclusivamente na coluna da Chave Primária e converte o resultado para uma lista Python
        existentes = pd.read_sql(f"SELECT {pk_banco} FROM {nome_tabela}", engine)[pk_banco].tolist()
    # Captura a exceção caso a tabela esteja vazia ou não exista, assumindo que não há chaves cadastradas
    except:
        existentes = []

    # Aplica o filtro de exclusão: mantém apenas as linhas cuja PK convertida em string NÃO esteja na lista de existentes
    chaves_existentes = [str(x) for x in existentes]

    # Atualiza registros que ja existem para refletir alteracoes do arquivo mais recente
    df_existente = df[df[pk_banco].astype(str).isin(chaves_existentes)]
    atualizados = atualizar_registros_existentes(df_existente, nome_tabela, pk_banco)
    if atualizados > 0:
        print(f"\n[ATUALIZADO] {atualizados:,} registros existentes atualizados na tabela '{nome_tabela}'.")

    df_novo = df[~df[pk_banco].astype(str).isin(chaves_existentes)]

    # Verifica estruturalmente se o DataFrame resultante do filtro possui algum dado inédito
    if not df_novo.empty:
        # Executa a inserção dos dados novos no banco utilizando o método append para não sobrescrever o passado
        df_novo.to_sql(nome_tabela, engine, if_exists='append', index=False)
        # Emite alerta de sucesso informando a quantidade exata de registros inseridos
        print(f"\n[SUCESSO] {len(df_novo)} novos registros inseridos na tabela '{nome_tabela}'.")
    else:
        # Informa ao usuário que todos os dados do arquivo selecionado já constam no banco de dados
        print(f"\n[AVISO] Nenhum dado novo localizado. O banco ja possui esses registros para '{nome_tabela}'.")

    limpar_nulls_no_banco(nome_tabela)
    return True

# Função dedicada a apagar todos os registros de uma tabela com confirmação do usuário
def apagar_tabela(nome_tabela):
    from sqlalchemy import text

    inspetor = inspect(engine)
    tabelas_no_banco = inspetor.get_table_names()
    if nome_tabela not in CONFIG_TABELAS or nome_tabela not in tabelas_no_banco:
        print(f"\n[ERRO] Tabela invalida ou inexistente: '{nome_tabela}'.")
        return

    # Consulta quantos registros existem antes de apagar
    total = contar_registros(nome_tabela)
    print(f"\n[ATENCAO] A tabela '{nome_tabela}' possui {total:,} registros.")

    if total == 0:
        print("[AVISO] A tabela ja esta vazia. Nenhum dado foi apagado.")
        return

    confirmacao = input(f"Digite 'CONFIRMAR' para apagar TODOS os registros: ")
    if confirmacao.strip().upper() != 'CONFIRMAR':
        print("\n[CANCELADO] Nenhum dado foi apagado.")
        return

    tabela_sql = escapar_identificador_sql(nome_tabela)
    try:
        # Libera todas as conexões abertas no pool antes de escrever (evita 'database is locked')
        engine.dispose()
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {tabela_sql}"))

            # Se a tabela usar AUTOINCREMENT em alguma versao futura, reinicia a sequencia tambem.
            sqlite_sequence_existe = conn.execute(text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
            )).scalar_one()
            if sqlite_sequence_existe:
                conn.execute(
                    text("DELETE FROM sqlite_sequence WHERE name = :nome_tabela"),
                    {"nome_tabela": nome_tabela}
                )

        restante = contar_registros(nome_tabela)
        print(f"\n[APAGADO] {total:,} registros removidos da tabela '{nome_tabela}'.")
        print(f"[OK] Registros restantes: {restante:,}.")
    except Exception as e:
        print(f"\n[ERRO] Nao foi possivel apagar os registros da tabela '{nome_tabela}': {e}")

# Função dedicada a abrir a interface gráfica do Windows para seleção de arquivos
def selecionar_arquivos():
    # Inicializa a instância principal da interface gráfica do Tkinter
    root = tk.Tk()
    # Oculta a janela raiz em branco, mantendo visível apenas a caixa de diálogo de arquivos
    root.withdraw()
    # Força a caixa de diálogo a aparecer na frente do terminal CMD
    root.attributes('-topmost', True)
    pasta_dados = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dados')
    pasta_inicial = pasta_dados if os.path.isdir(pasta_dados) else os.path.dirname(os.path.abspath(__file__))
    # Abre o explorador de arquivos filtrando visualmente apenas extensões de dados (CSV e XLSX)
    caminhos = filedialog.askopenfilenames(
        title="Selecione os arquivos para importar",
        initialdir=pasta_inicial,
        filetypes=[("Arquivos de Dados", "*.csv *.xlsx *.xls *.xlsm *.xlsb *.html *.htm"), ("Todos os Arquivos", "*.*")]
    )
    # Retorna o diretório em formato string do arquivo escolhido pelo usuário
    return caminhos

# Função principal responsável por desenhar o menu iterativo no terminal do usuário
def menu_interativo():
    # Instancia o inspetor para verificar quais tabelas físicas existem no SQLite
    inspetor = inspect(engine)
    # Coleta os nomes de todas as tabelas criadas no banco de dados
    tabelas_no_banco = inspetor.get_table_names()
    
    # Validação de segurança: trava a execução se o banco estiver vazio
    if not tabelas_no_banco:
        print("[ERRO] Nenhuma tabela encontrada no banco de dados. Rode o script de criacao primeiro.")
        return

    # Inicia um loop infinito para que o programa não feche após importar apenas um arquivo
    while True:
        # Desenha a interface visual do menu no console CMD
        print("\n======================================================")
        print("        IMPORTADOR INTERATIVO")
        print("======================================================")
        print("Tabelas disponiveis no banco de dados:\n")
        
        # Filtra a lista de tabelas para mostrar apenas aquelas que mapeamos no CONFIG_TABELAS
        tabelas_validas = [t for t in tabelas_no_banco if t in CONFIG_TABELAS.keys()]
        
        # Enumera a lista de tabelas válidas a partir do índice 1 para facilitar a digitação pelo usuário
        for i, tabela in enumerate(tabelas_validas, 1):
            total = pd.read_sql(f"SELECT COUNT(*) as n FROM {tabela}", engine)['n'][0]
            print(f"[{i}] - {tabela}  ({total:,} registros)")
        
        # Oferece uma opção de saída controlada do loop
        print("[0] - Sair")
        print("======================================================")
        
        # Fica aguardando o usuário digitar um número e apertar Enter
        escolha = input("Digite o numero da tabela: ")
        
        # Interrompe o loop infinito e encerra o sistema se a escolha for zero
        if escolha == '0':
            print("Encerrando o sistema...")
            break
        
        # Tenta converter o texto digitado pelo usuário em um número inteiro
        try:
            # Subtrai 1 para alinhar o número digitado (ex: 1) com o índice da lista em Python (ex: 0)
            indice = int(escolha) - 1
            # Verifica se o índice processado pertence de fato a uma tabela da lista válida
            if 0 <= indice < len(tabelas_validas):
                # Armazena o nome da tabela baseada na escolha matemática do usuário
                tabela_escolhida = tabelas_validas[indice]

                # Sub-menu de ação
                print(f"\nTabela selecionada: {tabela_escolhida}")
                print("------------------------------------------------------")
                print("[1] - Importar dados")
                print("[2] - Apagar todos os registros")
                print("[0] - Voltar")
                print("------------------------------------------------------")
                acao = input("Digite a acao desejada: ").strip()

                if acao == '1':
                    print("\nAbrindo o explorador de arquivos. Selecione um ou mais relatorios...")
                    # Interrompe o terminal temporariamente até o usuário escolher um arquivo na janela gráfica
                    arquivos_escolhidos = selecionar_arquivos()
                    # Valida se o usuário efetivamente escolheu um arquivo ou se clicou em 'Cancelar'
                    if arquivos_escolhidos:
                        print(f"Arquivos selecionados: {len(arquivos_escolhidos)}")
                        print("Processando os dados, hiper foco ativado...")
                        # Acessa o dicionário dinamicamente para pegar a Chave Primária específica desta tabela
                        pk = CONFIG_TABELAS[tabela_escolhida]['pk']
                        # Acessa o dicionário dinamicamente para pegar o mapeamento de colunas específico desta tabela
                        mapeamento = CONFIG_TABELAS[tabela_escolhida]['map']
                        # Dispara o gatilho da função ETL passando as informações amarradas pelo usuário
                        for indice, arquivo_escolhido in enumerate(arquivos_escolhidos, 1):
                            print(f"\n[ARQUIVO {indice}/{len(arquivos_escolhidos)}] {arquivo_escolhido}")
                            executar_etl(arquivo_escolhido, tabela_escolhida, pk, mapeamento)
                    else:
                        # Avisa caso o usuário tenha fechado a janela de arquivos sem escolher nada
                        print("\n[AVISO] Selecao de arquivos cancelada pelo usuario.")

                elif acao == '2':
                    apagar_tabela(tabela_escolhida)

                elif acao == '0':
                    print("Voltando ao menu principal...")
                else:
                    print("\n[ERRO] Opcao invalida.")
            else:
                # Avisa caso o usuário digite um número que não está na lista de tabelas
                print("\n[ERRO] Opcao invalida. Tente novamente.")
        # Captura o erro caso o usuário digite uma letra ou caractere especial em vez de um número
        except ValueError:
            print("\n[ERRO] Comando invalido. Por favor, digite apenas os numeros indicados no menu.")

# Condição de execução que dispara o menu caso este arquivo seja rodado diretamente
if __name__ == "__main__":
    menu_interativo()
