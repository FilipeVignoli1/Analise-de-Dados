import contextlib
import io
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import importador

try:
    import customtkinter as ctk
    from PIL import Image, ImageDraw
    HAS_CUSTOMTKINTER = True
except ImportError:
    HAS_CUSTOMTKINTER = False

    class _CustomTkinterAusente:
        CTk = object

    ctk = _CustomTkinterAusente()


APP_TITLE = "GEREL Produtividade | Importador"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DADOS_DIR = os.path.join(BASE_DIR, "dados")
APP_ICON = os.path.join(BASE_DIR, "assets", "app_icon.ico")
LOG_PATH = os.path.join(BASE_DIR, "importador_ultimo_log.txt")


def formatar_numero(valor):
    return f"{valor:,}".replace(",", ".")


def limpar_log_arquivo():
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as arquivo:
            arquivo.write("")
    except OSError:
        pass


def gravar_log_arquivo(texto):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto)
    except OSError:
        pass


class LogRedirector(contextlib.AbstractContextManager):
    def __init__(self, callback):
        self.callback = callback
        self.buffer = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.buffer)

    def __enter__(self):
        self.redirect.__enter__()
        return self

    def __exit__(self, exc_type, exc, exc_tb):
        self.redirect.__exit__(exc_type, exc, exc_tb)
        texto = self.buffer.getvalue()
        if texto:
            self.callback(texto)
        return False


class AppCustomTkinter(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(1060, 680)
        if os.path.exists(APP_ICON):
            self.iconbitmap(APP_ICON)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.tabelas = [t for t in importador.CONFIG_TABELAS if t in importador.inspect(importador.engine).get_table_names()]
        self.tabela_var = ctk.StringVar(value=self.tabelas[0] if self.tabelas else "")
        self.status_var = ctk.StringVar(value="Sistema pronto")
        self.arquivo_var = ctk.StringVar(value="Nenhum arquivo selecionado")
        self.contadores = {}
        self.icons = self._criar_icones()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._criar_sidebar()
        self._criar_conteudo()
        self.atualizar_contadores()

    def _criar_icones(self):
        nomes = ["database", "upload", "trash", "refresh", "folder", "activity", "table", "check", "shield"]
        return {nome: self._criar_icone(nome) for nome in nomes}

    def _criar_icone(self, nome, cor="#e8f3ff"):
        tamanho = 26
        img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        w = 2

        if nome == "database":
            draw.ellipse((5, 4, 21, 10), outline=cor, width=w)
            draw.line((5, 7, 5, 18), fill=cor, width=w)
            draw.line((21, 7, 21, 18), fill=cor, width=w)
            draw.ellipse((5, 15, 21, 22), outline=cor, width=w)
        elif nome == "upload":
            draw.line((13, 5, 13, 17), fill=cor, width=w)
            draw.line((8, 10, 13, 5, 18, 10), fill=cor, width=w)
            draw.rounded_rectangle((5, 16, 21, 22), radius=3, outline=cor, width=w)
        elif nome == "trash":
            draw.rounded_rectangle((7, 9, 19, 22), radius=2, outline=cor, width=w)
            draw.line((5, 7, 21, 7), fill=cor, width=w)
            draw.line((10, 5, 16, 5), fill=cor, width=w)
            draw.line((11, 12, 11, 19), fill=cor, width=1)
            draw.line((15, 12, 15, 19), fill=cor, width=1)
        elif nome == "refresh":
            draw.arc((5, 5, 21, 21), 35, 310, fill=cor, width=w)
            draw.line((19, 5, 21, 11, 15, 10), fill=cor, width=w)
        elif nome == "folder":
            draw.rounded_rectangle((4, 8, 22, 21), radius=3, outline=cor, width=w)
            draw.line((4, 10, 10, 10, 12, 7, 18, 7, 20, 10), fill=cor, width=w)
        elif nome == "activity":
            draw.line((4, 14, 9, 14, 11, 8, 15, 19, 18, 12, 22, 12), fill=cor, width=w)
        elif nome == "table":
            draw.rounded_rectangle((5, 5, 21, 21), radius=3, outline=cor, width=w)
            draw.line((5, 11, 21, 11), fill=cor, width=w)
            draw.line((11, 5, 11, 21), fill=cor, width=w)
        elif nome == "check":
            draw.line((6, 14, 11, 19, 21, 8), fill=cor, width=3)
        elif nome == "shield":
            draw.polygon([(13, 4), (21, 8), (19, 18), (13, 23), (7, 18), (5, 8)], outline=cor)
            draw.line((9, 13, 12, 16, 17, 10), fill=cor, width=w)

        return ctk.CTkImage(light_image=img, dark_image=img, size=(22, 22))

    def _criar_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=310, corner_radius=0, fg_color="#101828")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(9, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=22, pady=(26, 20), sticky="ew")
        brand.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkFrame(brand, width=48, height=48, corner_radius=12, fg_color="#1677ff")
        badge.grid(row=0, column=0, rowspan=2, sticky="w")
        badge.grid_propagate(False)
        ctk.CTkLabel(badge, text="G", font=ctk.CTkFont(size=24, weight="bold")).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(brand, text="GEREL", font=ctk.CTkFont(size=25, weight="bold")).grid(
            row=0, column=1, padx=12, sticky="sw"
        )
        ctk.CTkLabel(brand, text="Central de importacao", text_color="#98a2b3").grid(row=1, column=1, padx=12, sticky="nw")

        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="ew")
        nav.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(nav, text="  Importador", image=self.icons["upload"], anchor="w", height=42).grid(
            row=0, column=0, sticky="ew", pady=4
        )
        ctk.CTkButton(
            nav,
            text="  Banco de dados",
            image=self.icons["database"],
            anchor="w",
            height=42,
            fg_color="#182230",
            hover_color="#1d2939",
        ).grid(row=1, column=0, sticky="ew", pady=4)

        ctk.CTkLabel(sidebar, text="TABELA ATIVA", text_color="#98a2b3", font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=2, column=0, padx=22, pady=(6, 6), sticky="w"
        )
        self.combo_tabelas = ctk.CTkOptionMenu(
            sidebar,
            values=self.tabelas,
            variable=self.tabela_var,
            command=lambda _: self.atualizar_status_tabela(),
            height=38,
            fg_color="#1d2939",
            button_color="#1677ff",
            button_hover_color="#0b5fcc",
        )
        self.combo_tabelas.grid(row=3, column=0, padx=22, pady=(0, 16), sticky="ew")

        for idx, tabela in enumerate(self.tabelas, start=4):
            card = ctk.CTkFrame(sidebar, corner_radius=10, fg_color="#182230")
            card.grid(row=idx, column=0, padx=18, pady=6, sticky="ew")
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text="", image=self.icons["table"]).grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=12)
            ctk.CTkLabel(card, text=tabela, text_color="#d0d5dd", font=ctk.CTkFont(size=12, weight="bold")).grid(
                row=0, column=1, padx=(0, 12), pady=(10, 0), sticky="w"
            )
            label = ctk.CTkLabel(card, text="0 registros", font=ctk.CTkFont(size=17, weight="bold"))
            label.grid(row=1, column=1, padx=(0, 12), pady=(0, 10), sticky="w")
            self.contadores[tabela] = label

        status_card = ctk.CTkFrame(sidebar, corner_radius=12, fg_color="#0b5fcc")
        status_card.grid(row=10, column=0, padx=18, pady=(12, 20), sticky="sew")
        status_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(status_card, text="", image=self.icons["shield"]).grid(row=0, column=0, padx=(14, 8), pady=14)
        ctk.CTkLabel(status_card, textvariable=self.status_var, wraplength=210, justify="left", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=1, padx=(0, 14), pady=14, sticky="w"
        )

    def _criar_conteudo(self):
        conteudo = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        conteudo.grid(row=0, column=1, sticky="nsew", padx=28, pady=26)
        conteudo.grid_columnconfigure(0, weight=1)
        conteudo.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(conteudo, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Importador de Dados", font=ctk.CTkFont(size=30, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Banco SQLite consolidado para produtividade GEREL", text_color="#98a2b3").grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        ctk.CTkButton(
            header,
            text="Atualizar",
            image=self.icons["refresh"],
            width=132,
            height=38,
            fg_color="#182230",
            hover_color="#1d2939",
            command=self.atualizar_contadores,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        resumo = ctk.CTkFrame(conteudo, fg_color="transparent")
        resumo.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        resumo.grid_columnconfigure((0, 1, 2), weight=1)

        self.card_tabela = self._criar_card_info(resumo, 0, "Tabela selecionada", self.tabela_var.get(), "database")
        self.card_arquivo = self._criar_card_info(resumo, 1, "Arquivos", self.arquivo_var.get(), "folder")
        self.card_atividade = self._criar_card_info(resumo, 2, "Atividade", "Pronto para operar", "activity")

        acoes = ctk.CTkFrame(conteudo, corner_radius=12, fg_color="#182230")
        acoes.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        acoes.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_importar = ctk.CTkButton(
            acoes,
            text="  Importar arquivos",
            image=self.icons["upload"],
            command=self.importar_arquivo,
            height=46,
            corner_radius=10,
        )
        self.btn_importar.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        self.btn_apagar = ctk.CTkButton(
            acoes,
            text="  Apagar registros",
            image=self.icons["trash"],
            fg_color="#9b1c1c",
            hover_color="#7f1d1d",
            command=self.apagar_registros,
            height=46,
            corner_radius=10,
        )
        self.btn_apagar.grid(row=0, column=1, padx=12, pady=12, sticky="ew")
        self.btn_atualizar = ctk.CTkButton(
            acoes,
            text="  Sincronizar painel",
            image=self.icons["refresh"],
            command=self.atualizar_contadores,
            height=46,
            corner_radius=10,
            fg_color="#344054",
            hover_color="#475467",
        )
        self.btn_atualizar.grid(row=0, column=2, padx=12, pady=12, sticky="ew")

        painel = ctk.CTkFrame(conteudo, corner_radius=14, fg_color="#101828")
        painel.grid(row=3, column=0, sticky="nsew")
        painel.grid_columnconfigure(0, weight=1)
        painel.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(painel, text="Sistema pronto para importacao", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=22, pady=(24, 4), sticky="w"
        )
        ctk.CTkLabel(
            painel,
            text=f"Arquivos serao buscados automaticamente em: {DADOS_DIR}",
            text_color="#98a2b3",
        ).grid(row=1, column=0, padx=22, pady=(0, 18), sticky="w")

        trilha = ctk.CTkFrame(painel, fg_color="transparent")
        trilha.grid(row=2, column=0, padx=22, pady=(0, 22), sticky="new")
        trilha.grid_columnconfigure((0, 1, 2), weight=1)
        self._criar_passo(trilha, 0, "1", "Escolha a tabela")
        self._criar_passo(trilha, 1, "2", "Importe os arquivos")
        self._criar_passo(trilha, 2, "3", "Confira os contadores")

        ctk.CTkLabel(painel, text="Log da importacao", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, padx=22, pady=(0, 6), sticky="nw"
        )
        self.log = ctk.CTkTextbox(painel, font=("Consolas", 11), wrap="word", fg_color="#0b1220")
        self.log.grid(row=4, column=0, padx=22, pady=(0, 22), sticky="nsew")
        self.log.configure(state="disabled")
        self.escrever_log("Sistema iniciado.\n")
        self.escrever_log(f"Pasta de arquivos: {DADOS_DIR}\n\n")

    def _criar_card_info(self, parent, coluna, titulo, valor, icone):
        card = ctk.CTkFrame(parent, corner_radius=12, fg_color="#182230")
        card.grid(row=0, column=coluna, padx=(0 if coluna == 0 else 8, 0 if coluna == 2 else 8), sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="", image=self.icons[icone]).grid(row=0, column=0, rowspan=2, padx=(16, 10), pady=16)
        ctk.CTkLabel(card, text=titulo.upper(), text_color="#98a2b3", font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=0, column=1, padx=(0, 14), pady=(14, 0), sticky="w"
        )
        label = ctk.CTkLabel(card, text=valor, font=ctk.CTkFont(size=15, weight="bold"), anchor="w")
        label.grid(row=1, column=1, padx=(0, 14), pady=(0, 14), sticky="ew")
        return label

    def _criar_passo(self, parent, coluna, numero, texto):
        passo = ctk.CTkFrame(parent, corner_radius=12, fg_color="#182230")
        passo.grid(row=0, column=coluna, padx=(0 if coluna == 0 else 8, 0 if coluna == 2 else 8), sticky="ew")
        bolha = ctk.CTkFrame(passo, width=34, height=34, corner_radius=17, fg_color="#1677ff")
        bolha.grid(row=0, column=0, padx=14, pady=14)
        bolha.grid_propagate(False)
        ctk.CTkLabel(bolha, text=numero, font=ctk.CTkFont(size=14, weight="bold")).place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(passo, text=texto, font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=1, padx=(0, 14), pady=14, sticky="w"
        )

    def escrever_log(self, texto):
        gravar_log_arquivo(texto)
        self.after(0, self._escrever_log, texto)

    def _escrever_log(self, texto):
        texto_limpo = texto.strip()
        if texto_limpo and hasattr(self, "card_atividade"):
            ultima_linha = texto_limpo.splitlines()[-1]
            self.card_atividade.configure(text=ultima_linha[:80])
        if hasattr(self, "log"):
            self.log.configure(state="normal")
            self.log.insert("end", texto)
            self.log.see("end")
            self.log.configure(state="disabled")

    def executar_em_thread(self, descricao, func):
        self.status_var.set(descricao)
        if hasattr(self, "card_atividade"):
            self.card_atividade.configure(text=descricao)
        self.btn_importar.configure(state="disabled")
        self.btn_apagar.configure(state="disabled")
        self.btn_atualizar.configure(state="disabled")

        def alvo():
            try:
                func()
            except Exception as erro:
                self.escrever_log(f"\n[ERRO] {erro}\n")
            finally:
                self.after(0, self.atualizar_contadores)
                self.after(0, lambda: self.status_var.set("Sistema pronto"))
                self.after(0, lambda: self.card_atividade.configure(text="Pronto para operar"))
                self.after(0, lambda: self.btn_importar.configure(state="normal"))
                self.after(0, lambda: self.btn_apagar.configure(state="normal"))
                self.after(0, lambda: self.btn_atualizar.configure(state="normal"))

        threading.Thread(target=alvo, daemon=True).start()

    def atualizar_status_tabela(self):
        tabela = self.tabela_var.get()
        total = importador.contar_registros(tabela) if tabela else 0
        self.status_var.set(f"{tabela}: {formatar_numero(total)} registros")
        if hasattr(self, "card_tabela"):
            self.card_tabela.configure(text=tabela)

    def atualizar_contadores(self):
        for tabela, label in self.contadores.items():
            try:
                total = importador.contar_registros(tabela)
                label.configure(text=f"{formatar_numero(total)} registros")
            except Exception:
                label.configure(text="erro ao contar")
        self.atualizar_status_tabela()

    def importar_arquivo(self):
        tabela = self.tabela_var.get()
        if not tabela:
            messagebox.showwarning("Tabela", "Selecione uma tabela.")
            return

        caminhos = filedialog.askopenfilenames(
            title="Selecione os arquivos para importar",
            initialdir=DADOS_DIR if os.path.isdir(DADOS_DIR) else BASE_DIR,
            filetypes=[("Arquivos de Dados", "*.csv *.xlsx *.xls *.xlsm *.xlsb *.html *.htm"), ("Todos os Arquivos", "*.*")],
        )
        if not caminhos:
            return
        limpar_log_arquivo()

        nomes_arquivos = [os.path.basename(caminho) for caminho in caminhos]
        texto_arquivos = nomes_arquivos[0] if len(nomes_arquivos) == 1 else f"{len(nomes_arquivos)} arquivos selecionados"
        self.arquivo_var.set(texto_arquivos)
        if hasattr(self, "card_arquivo"):
            self.card_arquivo.configure(text=texto_arquivos)

        def tarefa():
            cfg = importador.CONFIG_TABELAS[tabela]
            total_arquivos = len(caminhos)
            total_antes = importador.contar_registros(tabela)
            falhas = 0
            self.escrever_log(f"\n[IMPORTACAO] Tabela: {tabela}\nArquivos selecionados: {total_arquivos}\n")
            for indice, caminho in enumerate(caminhos, 1):
                self.escrever_log(f"\n[ARQUIVO {indice}/{total_arquivos}] {caminho}\n")
                try:
                    antes_arquivo = importador.contar_registros(tabela)
                    with LogRedirector(self.escrever_log):
                        importacao_ok = importador.executar_etl(caminho, tabela, cfg["pk"], cfg["map"])
                    if importacao_ok is False:
                        falhas += 1
                    depois_arquivo = importador.contar_registros(tabela)
                    inseridos_arquivo = depois_arquivo - antes_arquivo
                    if inseridos_arquivo > 0:
                        self.escrever_log(f"[OK] {formatar_numero(inseridos_arquivo)} registros inseridos por este arquivo.\n")
                    else:
                        self.escrever_log("[INFO] Este arquivo nao inseriu registros novos.\n")
                except Exception as erro:
                    falhas += 1
                    self.escrever_log(f"[ERRO] Falha ao importar este arquivo: {erro}\n")
            total_depois = importador.contar_registros(tabela)
            inseridos_total = total_depois - total_antes
            resumo = (
                f"Arquivos processados: {total_arquivos}\n"
                f"Registros inseridos: {formatar_numero(inseridos_total)}\n"
                f"Falhas: {falhas}\n"
                f"Total atual na tabela: {formatar_numero(total_depois)}"
            )
            self.escrever_log(f"[FIM] Importacao concluida.\n{resumo}\n")
            self.after(0, lambda: messagebox.showinfo("Importacao finalizada", resumo))

        self.executar_em_thread("Importando arquivos...", tarefa)

    def apagar_registros(self):
        tabela = self.tabela_var.get()
        if not tabela:
            messagebox.showwarning("Tabela", "Selecione uma tabela.")
            return

        total = importador.contar_registros(tabela)
        if total == 0:
            messagebox.showinfo("Apagar registros", "A tabela ja esta vazia.")
            return

        confirmar = messagebox.askyesno(
            "Confirmar exclusao",
            f"Apagar todos os {formatar_numero(total)} registros da tabela '{tabela}'?",
        )
        if not confirmar:
            return

        def tarefa():
            from sqlalchemy import text

            tabela_sql = importador.escapar_identificador_sql(tabela)
            self.escrever_log(f"\n[APAGAR] Tabela: {tabela}\n")
            with importador.engine.begin() as conn:
                conn.execute(text(f"DELETE FROM {tabela_sql}"))
            self.escrever_log(f"[APAGADO] {formatar_numero(total)} registros removidos.\n")

        self.executar_em_thread("Apagando registros...", tarefa)


class AppTkinter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x620")
        self.minsize(900, 560)
        if os.path.exists(APP_ICON):
            self.iconbitmap(APP_ICON)

        self.tabelas = [t for t in importador.CONFIG_TABELAS if t in importador.inspect(importador.engine).get_table_names()]
        self.tabela_var = tk.StringVar(value=self.tabelas[0] if self.tabelas else "")
        self.status_var = tk.StringVar(value="Sistema pronto")

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, padding=18)
        sidebar.grid(row=0, column=0, sticky="nsew")

        ttk.Label(sidebar, text="GEREL Produtividade", font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 18))
        ttk.Label(sidebar, text="Tabela selecionada").pack(anchor="w")
        self.combo = ttk.Combobox(sidebar, values=self.tabelas, textvariable=self.tabela_var, state="readonly", width=34)
        self.combo.pack(anchor="w", pady=(4, 18))
        self.combo.bind("<<ComboboxSelected>>", lambda _: self.atualizar_contadores())

        self.contadores = {}
        for tabela in self.tabelas:
            frame = ttk.LabelFrame(sidebar, text=tabela, padding=10)
            frame.pack(fill="x", pady=5)
            label = ttk.Label(frame, text="0 registros", font=("Segoe UI", 12, "bold"))
            label.pack(anchor="w")
            self.contadores[tabela] = label

        ttk.Label(sidebar, textvariable=self.status_var, wraplength=240).pack(anchor="sw", side="bottom")

        main = ttk.Frame(self, padding=18)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        ttk.Label(main, text="Importador de Dados", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        buttons = ttk.Frame(main)
        buttons.grid(row=1, column=0, sticky="ew", pady=14)
        self.btn_importar = ttk.Button(buttons, text="Importar arquivos", command=self.importar_arquivo)
        self.btn_importar.pack(side="left", padx=(0, 8))
        self.btn_apagar = ttk.Button(buttons, text="Apagar registros", command=self.apagar_registros)
        self.btn_apagar.pack(side="left", padx=8)
        self.btn_atualizar = ttk.Button(buttons, text="Atualizar contadores", command=self.atualizar_contadores)
        self.btn_atualizar.pack(side="left", padx=8)

        self.log = tk.Text(main, font=("Consolas", 10), wrap="word")
        self.log.grid(row=2, column=0, sticky="nsew")
        self.escrever_log("Sistema iniciado.\n")
        self.escrever_log(f"Pasta de arquivos: {DADOS_DIR}\n\n")
        self.atualizar_contadores()

    def escrever_log(self, texto):
        gravar_log_arquivo(texto)
        self.after(0, lambda: (self.log.insert("end", texto), self.log.see("end")))

    def executar_em_thread(self, descricao, func):
        self.status_var.set(descricao)
        for botao in (self.btn_importar, self.btn_apagar, self.btn_atualizar):
            botao.configure(state="disabled")

        def alvo():
            try:
                func()
            except Exception as erro:
                self.escrever_log(f"\n[ERRO] {erro}\n")
            finally:
                self.after(0, self.atualizar_contadores)
                self.after(0, lambda: self.status_var.set("Sistema pronto"))
                for botao in (self.btn_importar, self.btn_apagar, self.btn_atualizar):
                    self.after(0, lambda b=botao: b.configure(state="normal"))

        threading.Thread(target=alvo, daemon=True).start()

    def atualizar_contadores(self):
        for tabela, label in self.contadores.items():
            try:
                total = importador.contar_registros(tabela)
                label.configure(text=f"{formatar_numero(total)} registros")
            except Exception:
                label.configure(text="erro ao contar")
        tabela = self.tabela_var.get()
        if tabela:
            self.status_var.set(f"{tabela}: {formatar_numero(importador.contar_registros(tabela))} registros")

    def importar_arquivo(self):
        tabela = self.tabela_var.get()
        caminhos = filedialog.askopenfilenames(
            title="Selecione os arquivos para importar",
            initialdir=DADOS_DIR if os.path.isdir(DADOS_DIR) else BASE_DIR,
            filetypes=[("Arquivos de Dados", "*.csv *.xlsx *.xls *.xlsm *.xlsb *.html *.htm"), ("Todos os Arquivos", "*.*")],
        )
        if not caminhos:
            return
        limpar_log_arquivo()

        def tarefa():
            cfg = importador.CONFIG_TABELAS[tabela]
            total_arquivos = len(caminhos)
            total_antes = importador.contar_registros(tabela)
            falhas = 0
            self.escrever_log(f"\n[IMPORTACAO] Tabela: {tabela}\nArquivos selecionados: {total_arquivos}\n")
            for indice, caminho in enumerate(caminhos, 1):
                self.escrever_log(f"\n[ARQUIVO {indice}/{total_arquivos}] {caminho}\n")
                try:
                    antes_arquivo = importador.contar_registros(tabela)
                    with LogRedirector(self.escrever_log):
                        importacao_ok = importador.executar_etl(caminho, tabela, cfg["pk"], cfg["map"])
                    if importacao_ok is False:
                        falhas += 1
                    depois_arquivo = importador.contar_registros(tabela)
                    inseridos_arquivo = depois_arquivo - antes_arquivo
                    if inseridos_arquivo > 0:
                        self.escrever_log(f"[OK] {formatar_numero(inseridos_arquivo)} registros inseridos por este arquivo.\n")
                    else:
                        self.escrever_log("[INFO] Este arquivo nao inseriu registros novos.\n")
                except Exception as erro:
                    falhas += 1
                    self.escrever_log(f"[ERRO] Falha ao importar este arquivo: {erro}\n")
            total_depois = importador.contar_registros(tabela)
            inseridos_total = total_depois - total_antes
            resumo = (
                f"Arquivos processados: {total_arquivos}\n"
                f"Registros inseridos: {formatar_numero(inseridos_total)}\n"
                f"Falhas: {falhas}\n"
                f"Total atual na tabela: {formatar_numero(total_depois)}"
            )
            self.escrever_log(f"[FIM] Importacao concluida.\n{resumo}\n")
            self.after(0, lambda: messagebox.showinfo("Importacao finalizada", resumo))

        self.executar_em_thread("Importando arquivos...", tarefa)

    def apagar_registros(self):
        tabela = self.tabela_var.get()
        total = importador.contar_registros(tabela)
        if total == 0:
            messagebox.showinfo("Apagar registros", "A tabela ja esta vazia.")
            return
        if not messagebox.askyesno("Confirmar exclusao", f"Apagar todos os {formatar_numero(total)} registros de '{tabela}'?"):
            return

        def tarefa():
            from sqlalchemy import text

            tabela_sql = importador.escapar_identificador_sql(tabela)
            self.escrever_log(f"\n[APAGAR] Tabela: {tabela}\n")
            with importador.engine.begin() as conn:
                conn.execute(text(f"DELETE FROM {tabela_sql}"))
            self.escrever_log(f"[APAGADO] {formatar_numero(total)} registros removidos.\n")

        self.executar_em_thread("Apagando registros...", tarefa)


def main():
    if HAS_CUSTOMTKINTER:
        app = AppCustomTkinter()
    else:
        app = AppTkinter()
        app.escrever_log("[AVISO] customtkinter nao instalado. Usando interface Tkinter padrao.\n")
        app.escrever_log("Para ativar o visual moderno: python -m pip install customtkinter\n\n")
    app.mainloop()


if __name__ == "__main__":
    main()
