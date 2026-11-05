"""
Minecraft Arcade — Jogo da Velha + Conect 4
Joy-Con gyro/analógico: pip install joycon-python hidapi pyglm
Pygame é opcional (fallback se PyJoyCon não importar): pip install pygame
Atalhos:
  Velha: CALIBRAR 9 CASAS; mire na casa 4 projetada, depois nas casas 0-3 e 5-8; B registra
  Casas contadas da esquerda para a direita, de cima para baixo, olhando para a projeção
  A calibração vale até fechar o programa ou mudar de posição; depois, repita-a
  Conect 4: analógico move a coluna; SR solta a peça (ajustável abaixo)
  Shift+1/2       -> Velha / Conect 4
  Shift+4       -> liga/desliga o Modo Botão (redstone na base por 2s)
  F11 / ESC   -> tela cheia
  R           -> reiniciar
  C           -> configurações
  1..9        -> casa do Jogo da Velha
"""

import copy
import datetime
import json
import math
import os
import queue
import random
import shutil
import platform
import subprocess
import urllib.request
import threading
import time
import tkinter as tk
from functools import lru_cache
from tkinter import filedialog, font as tkfont, messagebox

try:
    import pygame
except ImportError:
    pygame = None

try:
    from pyjoycon import GyroTrackingJoyCon, get_L_id, get_R_id
    PYJOYCON_AVAILABLE = True
except Exception:
    GyroTrackingJoyCon = get_L_id = get_R_id = None
    PYJOYCON_AVAILABLE = False

# ============================================================
# CONTROLES JOY-CON
# PyJoyCon identifica L=0/R=1; no fallback Pygame os índices variam por sistema.
# Use JOYCON_DEBUG=True para inspecionar e ajustar eixos/botões.
# ============================================================
JOYCON_ENABLED = True
JOYCON_DEBUG = False
JOYCON_POLL_MS = 12
JOYCON_UI_POLL_MS = 24
JOYCON_DEADZONE = 0.62
JOYCON_REPEAT_MS = 220
JOYCON_DEVICE_INDEX = (0, 1)       # L e R, respectivamente, no backend PyJoyCon
JOYCON_CONFIRM_BUTTON = (5, 5)     # botão SR para o modo analógico
JOYCON_C4_AXIS = (1, 1)            # eixo lateral ao segurar os Joy-Cons de lado
JOYCON_C4_INVERT = (False, True)   # inverter P1/P2 se o seletor andar ao contrário
JOYCON_TTT_AXES = ((0, 1), (0, 1)) # (eixo horizontal, eixo vertical) por jogador
JOYCON_TTT_SWAP_AXES = (True, True)
JOYCON_TTT_INVERT_X = (False, True)
JOYCON_TTT_INVERT_Y = (False, False)
JOYCON_GYRO_TTT_ENABLED = True
JOYCON_GYRO_DEVICE_INDEX = 1       # Joy-Con direito; necessário para o botão B
JOYCON_GYRO_CONFIRM_BUTTON = 1     # B no mapeamento PyJoyCon
JOYCON_GYRO_CALIBRATION_SECONDS = 1.5
JOYCON_GYRO_HALF_RANGE_DEG = 22.5  # centro até a borda do tabuleiro
JOYCON_GYRO_INVERT_X = False
JOYCON_GYRO_INVERT_Y = False

DELAY_MIN_IA_MS = 1000  # tempo mínimo exibindo "IA pensando..."

try:
    from mcrcon import MCRcon
    TEM_RCON = True
except ImportError:
    MCRcon = None
    TEM_RCON = False

PASTA_APLICATIVO = os.path.dirname(os.path.abspath(__file__))
# A configuração padrão fica embutida neste arquivo; não depende de .config.
ARQUIVO_PASTA_CONFIG = ""
DINOSSAUROS_DIFICULDADE = {
    "facil": {"nome": "T-Rex Roxo", "cor": "roxo", "id": "roxo", "pos": [100, 70, 200]},
    "medio": {"nome": "T-Rex Laranja", "cor": "laranja", "id": "laranja", "pos": [112, 70, 200]},
    "dificil": {"nome": "T-Rex Preto", "cor": "preto", "id": "preto", "pos": [124, 70, 200]},
    "impossivel": {"nome": "T-Rex Preto", "cor": "preto", "id": "preto", "pos": [124, 70, 200]},
}


def _obter_pasta_config():
    pasta_padrao = os.path.join(PASTA_APLICATIVO, "configs")
    try:
        if os.path.exists(ARQUIVO_PASTA_CONFIG):
            with open(ARQUIVO_PASTA_CONFIG, "r", encoding="utf-8") as f:
                pasta = f.read().strip()
            if pasta:
                pasta = os.path.abspath(os.path.expanduser(pasta))
                os.makedirs(pasta, exist_ok=True)
                return pasta
    except Exception:
        pass
    try:
        os.makedirs(pasta_padrao, exist_ok=True)
    except Exception:
        pasta_padrao = PASTA_APLICATIVO
    try:
        with open(ARQUIVO_PASTA_CONFIG, "w", encoding="utf-8") as f:
            f.write(os.path.abspath(pasta_padrao))
    except Exception:
        pass
    return os.path.abspath(pasta_padrao)


PASTA_CONFIG = PASTA_APLICATIVO
CAMINHO_CONFIG = ""

CONFIG_PADRAO = {'host': 'localhost',
 'porta': 25575,
 'senha': '131243',
 'usuario_op': '',
 'modo_offline': False,
 'bloco_base': 'redstone_block',
 'bloco_x': 'redstone_block',
 'bloco_o': 'air',
 'coordenadas': {'0': [-273, 111, -65],
                 '1': [-273, 111, -68],
                 '2': [-273, 111, -71],
                 '3': [-273, 108, -65],
                 '4': [-273, 108, -68],
                 '5': [-273, 108, -71],
                 '6': [-273, 105, -65],
                 '7': [-273, 105, -68],
                 '8': [-273, 105, -71]},
 'tela': {'tela_cheia': False,
          'largura': 1920,
          'altura': 1080,
          'escala': 1.0,
          'tamanho_tabuleiro': 560,
          'mostrar_simbolos': True,
          'mostrar_log': True,
          'largura_log': 340,
          'modo_feira': False,
          'modo_demo': False,
          'inatividade_segundos': 90},
 'tema': 'grafite',
 'nomes': {'X': 'Jogador', 'O': 'Jogador 2'},
 'console': {'historico_max': 200},
 'velha': {'modo': '2p', 'dificuldade': 'impossivel'},
 'conect4': {'coordenadas_colunas': {'0': [-276, 139, -120],
                                     '1': [-272, 139, -120],
                                     '2': [-268, 139, -120],
                                     '3': [-264, 139, -120],
                                     '4': [-260, 139, -120],
                                     '5': [-256, 139, -120],
                                     '6': [-252, 139, -120]},
             'colunas': 7,
             'linhas': 6,
             'dificuldade': 'impossivel',
             'modo': 'ia',
             'bloco_saida_on': 'redstone_block',
             'bloco_saida_off': 'air'},
 'hotspot': {'habilitar': False,
             'nome': 'PORTA ZERO',
             'senha': 'portazero0',
             'ip': '10.0.1.13/24',
             'nome_backup': 'PORTA ZERO backup',
             'desligar_sem_internet': True,
             'verificar_a_cada_segundos': 15,
             'interface': ''},
 'controles_minecraft': {'bloco_ligado': 'redstone_block',
                         'bloco_desligado': 'air',
                         'duracao_reset_ms': 2000,
                         'intervalo_min_jogadas_ms': 450,
                         'modo_botao': True,
                         'terracota_x': 'red_terracotta',
                         'terracota_o': 'blue_terracotta',
                         'terracota_p2': 'yellow_terracotta',
                         'velha': {'reset': [-284, 102, -62], 'jogador': [-276, 104, -62]},
                         'conect4': {'reset': [-282, 141, -116], 'jogador': [-279, 138, -105]}},
 'dinossauros': {'velha_x': {'nome': 'T-Rex', 'pos': [100, 70, 200]},
                 'velha_o': {'nome': 'Triceratops', 'pos': [112, 70, 200]},
                 'c4_p1': {'nome': 'Velociraptor', 'pos': [124, 70, 200]},
                 'c4_p2': {'nome': 'Anquilossauro', 'pos': [136, 70, 200]}}}

LINHAS_VITORIA = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]

SEGMENTOS = {
    "0": set("abcdef"), "1": set("bc"), "2": set("abdeg"), "3": set("abcdg"),
    "4": set("bcfg"), "5": set("acdfg"), "6": set("acdefg"), "7": set("abc"),
    "8": set("abcdefg"), "9": set("abcdfg"),
    "E": set("adefg"), "r": set("eg"), "-": set("g"), " ": set(),
}

DIFICULDADES = {
    "facil":      {"chance_aleatoria": 0.70, "profundidade": 1},
    "medio":      {"chance_aleatoria": 0.30, "profundidade": 3},
    "dificil":    {"chance_aleatoria": 0.00, "profundidade": 5},
    "impossivel": {"chance_aleatoria": 0.00, "profundidade": 7},
}

TEMAS = {
    "feira": {
        "fundo":"#09090d","painel":"#202026","campo":"#2b2b33","casa":"#24242b",
        "casa_hover":"#34343e","linha":"#41414b","x":"#ff5c74","o":"#54c8ff",
        "texto":"#f7f7fa","subtexto":"#9696a2","destaque":"#b9f46a",
        "erro":"#ff5c74","aviso":"#ffd166","vitoria":"#b9f46a",
    },
    "grafite": {
        "fundo":"#0e1721","painel":"#172431","campo":"#203241","casa":"#1d2d3a",
        "casa_hover":"#2b4658","linha":"#3e5b6d","x":"#ff7078","o":"#59c9b5",
        "texto":"#f1f6f8","subtexto":"#a8bac4","destaque":"#f2c96d",
        "erro":"#ff7078","aviso":"#f2c96d","vitoria":"#a9e6b5",
        "tabuleiro":"#27465b","slot":"#132738","slot_borda":"#3e6177",
        "sombra":"#09121a","x_borda":"#ffb0a9","o_borda":"#a9eee1",
    },
    "minecraft": {
        "fundo":"#111411","painel":"#222822","campo":"#303a30","casa":"#293329",
        "casa_hover":"#3b493b","linha":"#536153","x":"#f05b4f","o":"#54a8ff",
        "texto":"#f4f7f2","subtexto":"#a6afa3","destaque":"#72d35b",
        "erro":"#f05b4f","aviso":"#ffd25a","vitoria":"#ffd25a",
    },
}


def _mesclar(base, novo):
    for k, v in novo.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mesclar(base[k], v)
        else:
            base[k] = v
    return base


def carregar_config():
    # Não lê .config_folder nem config.json: usa somente o padrão embutido.
    cfg = copy.deepcopy(CONFIG_PADRAO)
    if cfg.get("tema") not in TEMAS:
        cfg["tema"] = "feira"
    if "velha" not in cfg:
        cfg["velha"] = {"modo": "ia", "dificuldade": "dificil"}
    if "conect4" not in cfg or not isinstance(cfg.get("conect4"), dict):
        cfg["conect4"] = copy.deepcopy(CONFIG_PADRAO["conect4"])
    if cfg["conect4"].get("modo") not in ("ia", "2p"):
        cfg["conect4"]["modo"] = "ia"
    c4 = cfg["conect4"]
    if not isinstance(c4.get("coordenadas_colunas"), dict) or len(c4.get("coordenadas_colunas", {})) != 7:
        antigas = c4.get("coordenadas", {})
        base = antigas.get("0,0", c4.get("origem", [0, 70, 0]))
        passo = int(c4.get("passo", 2))
        c4["coordenadas_colunas"] = {str(i): [int(base[0]) + i * passo, int(base[1]), int(base[2])] for i in range(7)}
    c4.setdefault("bloco_saida_on", "redstone_block")
    c4.setdefault("bloco_saida_off", "air")
    controles = cfg.setdefault("controles_minecraft", copy.deepcopy(CONFIG_PADRAO["controles_minecraft"]))
    controles.setdefault("bloco_ligado", "redstone_block")
    controles.setdefault("bloco_desligado", "air")
    controles.setdefault("duracao_reset_ms", 2000)
    controles.setdefault("intervalo_min_jogadas_ms", 450)
    controles.setdefault("modo_botao", True)
    controles.setdefault("terracota_x", "red_terracotta")
    controles.setdefault("terracota_o", "blue_terracotta")
    controles.setdefault("terracota_p2", "yellow_terracotta")
    controles.setdefault("velha", {}).setdefault("reset", [0, 70, 0])
    controles.setdefault("conect4", {}).setdefault("reset", [0, 70, 0])
    controles.setdefault("velha", {}).setdefault("jogador", [1, 70, 0])
    controles.setdefault("conect4", {}).setdefault("jogador", [3, 70, 0])
    cfg["tela"].setdefault("mostrar_simbolos", True)
    return cfg


def salvar_config(cfg):
    # As configurações padrão são mantidas no próprio main.py.
    return None


def _comando_sistema(args, timeout=12):
    """Executa um comando local sem shell; retorna (sucesso, saída)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           check=False)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def internet_disponivel():
    """Teste curto de internet, sem depender de ping ou de comandos externos."""
    try:
        with urllib.request.urlopen("https://connectivitycheck.gstatic.com/generate_204", timeout=4):
            return True
    except Exception:
        return False


class HotspotManager:
    """Gerencia o hotspot apenas quando explicitamente habilitado na configuração.

    Linux: NetworkManager/nmcli.
    Windows: netsh Hosted Network (quando o adaptador/Windows oferecer suporte).
    """
    def __init__(self, cfg, log=None):
        self.cfg = cfg or {}
        self.log = log or (lambda _msg: None)
        self.sistema = platform.system().lower()
        self.nome_ativo = None
        self._parar = threading.Event()
        self._thread = None

    def _info(self, msg):
        self.log("Hotspot: " + msg)

    def _nomes(self):
        base = str(self.cfg.get("nome", "PORTA ZERO")).strip() or "PORTA ZERO"
        backup = str(self.cfg.get("nome_backup", "")).strip() or (base + " backup")
        return base, backup

    def _linux_conexoes(self):
        ok, out = _comando_sistema(["nmcli", "-t", "-f", "NAME,UUID,TYPE,IP4.ADDRESS", "connection", "show"])
        return out.splitlines() if ok else []

    def _linux_escolher_nome(self):
        base, backup = self._nomes()
        linhas = self._linux_conexoes()
        nomes = {linha.split(":", 1)[0] for linha in linhas if ":" in linha}
        ip = str(self.cfg.get("ip", "10.0.1.13/24"))
        for nome in (base, backup):
            iguais = [l for l in linhas if l.startswith(nome + ":")]
            if not iguais:
                return nome
            if any(ip in l for l in iguais):
                return nome
        # Evita apagar uma rede desconhecida: cria uma terceira reserva.
        n = 2
        while f"{backup} {n}" in nomes:
            n += 1
        return f"{backup} {n}"

    def _linux_interface(self):
        if self.cfg.get("interface"):
            return str(self.cfg["interface"])
        ok, out = _comando_sistema(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
        if not ok:
            return ""
        for linha in out.splitlines():
            partes = linha.split(":")
            if len(partes) >= 2 and partes[1] == "wifi":
                return partes[0]
        return ""

    def _linux_up(self):
        nome = self._linux_escolher_nome()
        iface = self._linux_interface()
        if not iface:
            self._info("nenhuma interface Wi-Fi encontrada")
            return False
        senha = str(self.cfg.get("senha", "portazero0"))
        ip = str(self.cfg.get("ip", "10.0.1.13/24"))
        linhas = self._linux_conexoes()
        existe = any(l.startswith(nome + ":") and ip in l for l in linhas)
        if not existe:
            _comando_sistema(["nmcli", "connection", "delete", nome])
            ok, out = _comando_sistema(["nmcli", "connection", "add", "type", "wifi", "ifname", iface,
                                        "con-name", nome, "autoconnect", "no", "ssid", nome])
            if not ok:
                self._info("não foi possível criar a conexão: " + out)
                return False
            ok, out = _comando_sistema(["nmcli", "connection", "modify", nome,
                "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", senha,
                "ipv4.method", "shared", "ipv4.addresses", ip,
                "connection.autoconnect-priority", "0"])
            if not ok:
                self._info("não foi possível configurar a conexão: " + out)
                return False
        ok, out = _comando_sistema(["nmcli", "connection", "up", nome])
        if ok:
            self.nome_ativo = nome
            self._info(f"ativo: {nome} ({ip})")
        else:
            self._info("não foi possível ativar: " + out)
        return ok

    def _windows_up(self):
        nome, _ = self._nomes()
        senha = str(self.cfg.get("senha", "portazero0"))
        ok, out = _comando_sistema(["netsh", "wlan", "set", "hostednetwork", "mode=allow",
                                    f"ssid={nome}", f"key={senha}", "keyUsage=persistent"])
        if not ok:
            self._info("o adaptador/Windows não oferece Hosted Network: " + out)
            return False
        ok, out = _comando_sistema(["netsh", "wlan", "start", "hostednetwork"])
        if ok:
            self.nome_ativo = nome
            self._info("ativo: " + nome)
        else:
            self._info("não foi possível ativar: " + out)
        return ok

    def ligar(self):
        if self.sistema == "linux":
            return self._linux_up()
        if self.sistema == "windows":
            return self._windows_up()
        self._info("sistema não suportado: " + self.sistema)
        return False

    def desligar(self):
        if not self.nome_ativo and self.sistema == "linux":
            return True
        if self.sistema == "linux":
            ok, out = _comando_sistema(["nmcli", "connection", "down", self.nome_ativo])
        elif self.sistema == "windows":
            ok, out = _comando_sistema(["netsh", "wlan", "stop", "hostednetwork"])
        else:
            return False
        if ok: self._info("desligado")
        else: self._info("falha ao desligar: " + out)
        self.nome_ativo = None
        return ok

    def iniciar_monitor(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def _monitor(self):
        intervalo = max(5, int(self.cfg.get("verificar_a_cada_segundos", 15)))
        desligar = bool(self.cfg.get("desligar_sem_internet", True))
        while not self._parar.is_set():
            tem_internet = internet_disponivel()
            if desligar and not tem_internet and self.nome_ativo:
                self.desligar()
            elif tem_internet and not self.nome_ativo:
                self.ligar()
            self._parar.wait(intervalo)

    def parar(self):
        self._parar.set()
        if self.nome_ativo:
            self.desligar()


class JoyConReader:
    """Lê PyJoyCon (IMU) em segundo plano e usa Pygame só como fallback."""
    def __init__(self):
        self.fila = queue.Queue(maxsize=1)
        self.parar_evento = threading.Event()
        self.calibrar_evento = threading.Event()
        self.thread = threading.Thread(target=self._executar, name="joycon-reader", daemon=True)

    def iniciar(self):
        self.thread.start()

    def parar(self):
        self.parar_evento.set()

    def pedir_calibracao(self):
        self.calibrar_evento.set()

    def _publicar(self, valor):
        try:
            self.fila.put_nowait(valor)
        except queue.Full:
            try:
                self.fila.get_nowait()
            except queue.Empty:
                pass
            try:
                self.fila.put_nowait(valor)
            except queue.Full:
                pass

    @staticmethod
    def _stick_normalizado(valor):
        return max(-1.0, min(1.0, (float(valor) - 2048.0) / 2048.0))

    def _executar(self):
        if not JOYCON_ENABLED:
            self._publicar({"backend": "off", "error": "Leitura Joy-Con desativada em JOYCON_ENABLED."})
            return
        if PYJOYCON_AVAILABLE:
            self._executar_pyjoycon()
        else:
            self._executar_pygame()

    def _executar_pyjoycon(self):
        ativos = {}
        proxima_busca = 0.0
        erro = None
        while not self.parar_evento.is_set():
            agora = time.monotonic()
            if agora >= proxima_busca:
                try:
                    ids = {0: get_L_id(), 1: get_R_id()}
                    presentes = {i: id_ for i, id_ in ids.items()
                                 if id_ and id_[0] is not None and id_[1] is not None}
                    for indice in list(ativos):
                        if indice not in presentes or ativos[indice]["id"] != presentes[indice]:
                            ativos.pop(indice, None)
                    for indice, id_ in presentes.items():
                        if indice not in ativos:
                            try:
                                lado = "L" if indice == 0 else "R"
                                ativos[indice] = {
                                    "id": id_, "lado": lado,
                                    "joycon": GyroTrackingJoyCon(*id_),
                                    "calibrado": False, "calibrando": False,
                                    "fim_calibracao": 0.0,
                                }
                            except Exception as exc:
                                erro = f"PyJoyCon não abriu o Joy-Con {indice + 1}: {exc}"
                    if not presentes or all(i in ativos for i in presentes):
                        erro = None
                except Exception as exc:
                    erro = f"Falha ao localizar Joy-Con via HID: {exc}"
                proxima_busca = agora + 1.5

            if self.calibrar_evento.is_set():
                self.calibrar_evento.clear()
                alvo = ativos.get(JOYCON_GYRO_DEVICE_INDEX)
                if alvo:
                    alvo["joycon"].calibrate(seconds=JOYCON_GYRO_CALIBRATION_SECONDS)
                    alvo["calibrando"] = True
                    alvo["calibrado"] = False
                    alvo["fim_calibracao"] = time.monotonic() + JOYCON_GYRO_CALIBRATION_SECONDS + 0.2
                else:
                    erro = "Conecte o Joy-Con direito antes de calibrar a mira."

            controles = []
            for indice, registro in list(ativos.items()):
                jc = registro["joycon"]
                try:
                    if (registro["calibrando"] and not bool(jc.is_calibrating)
                            and time.monotonic() >= registro["fim_calibracao"]):
                        jc.reset_orientation()
                        registro["calibrando"] = False
                        registro["calibrado"] = True
                    status = jc.get_status()
                    stick = jc.stick_l if registro["lado"] == "L" else jc.stick_r
                    eixos = [self._stick_normalizado(stick[0]), self._stick_normalizado(stick[1]), 0.0, 0.0]
                    b = [False] * 16
                    botoes = status["buttons"]
                    if registro["lado"] == "L":
                        lateral = botoes["left"]
                        for pos, nome in ((0, "up"), (1, "down"), (2, "left"), (3, "right"),
                                          (4, "sl"), (5, "sr"), (14, "l"), (15, "zl")):
                            b[pos] = bool(lateral[nome])
                        b[8] = bool(botoes["shared"]["minus"])
                        b[10] = bool(botoes["shared"]["l-stick"])
                        b[13] = bool(botoes["shared"]["capture"])
                    else:
                        lateral = botoes["right"]
                        for pos, nome in ((0, "a"), (1, "b"), (2, "x"), (3, "y"),
                                          (4, "sl"), (5, "sr"), (14, "r"), (15, "zr")):
                            b[pos] = bool(lateral[nome])
                        b[9] = bool(botoes["shared"]["plus"])
                        b[11] = bool(botoes["shared"]["r-stick"])
                        b[12] = bool(botoes["shared"]["home"])
                    try:
                        mira = jc.pointer
                        ponteiro = [float(mira.x), float(mira.y)] if mira is not None else None
                    except Exception:
                        ponteiro = None
                    controles.append({
                        "index": indice,
                        "name": f"Joy-Con {registro['lado']}",
                        "axes": eixos,
                        "buttons": b,
                        "pointer": ponteiro,
                        "gyro": status.get("gyro", {}),
                        "gyro_calibrado": registro["calibrado"],
                        "gyro_calibrando": registro["calibrando"],
                    })
                except Exception as exc:
                    erro = f"Leitura do Joy-Con {indice + 1} falhou: {exc}"
            self._publicar({"backend": "pyjoycon", "devices": controles, "error": erro})
            self.parar_evento.wait(JOYCON_POLL_MS / 1000.0)

    def _executar_pygame(self):
        if pygame is None:
            self._publicar({"backend": "pygame", "devices": [],
                            "error": "Para gyro instale joycon-python hidapi pyglm; fallback analógico: pip install pygame."})
            return
        dispositivos = []
        try:
            pygame.display.init()
            pygame.joystick.init()
            quantidade_anterior = -1
            while not self.parar_evento.is_set():
                pygame.event.pump()
                quantidade = pygame.joystick.get_count()
                if quantidade != quantidade_anterior:
                    for dispositivo in dispositivos:
                        try: dispositivo.quit()
                        except Exception: pass
                    dispositivos = []
                    for indice in range(quantidade):
                        try:
                            dispositivo = pygame.joystick.Joystick(indice)
                            dispositivo.init()
                            dispositivos.append(dispositivo)
                        except Exception:
                            dispositivos.append(None)
                    quantidade_anterior = quantidade
                controles = []
                for indice, dispositivo in enumerate(dispositivos):
                    if dispositivo is None: continue
                    try:
                        controles.append({
                            "index": indice, "name": dispositivo.get_name(),
                            "axes": [float(dispositivo.get_axis(i)) for i in range(dispositivo.get_numaxes())],
                            "buttons": [bool(dispositivo.get_button(i)) for i in range(dispositivo.get_numbuttons())],
                            "pointer": None, "gyro_calibrado": False, "gyro_calibrando": False,
                        })
                    except Exception:
                        continue
                self._publicar({"backend": "pygame", "devices": controles})
                self.parar_evento.wait(JOYCON_POLL_MS / 1000.0)
        except Exception as exc:
            self._publicar({"backend": "pygame", "error": f"Falha ao iniciar leitura Pygame: {exc}"})
        finally:
            for dispositivo in dispositivos:
                try:
                    if dispositivo is not None: dispositivo.quit()
                except Exception:
                    pass
            try:
                pygame.joystick.quit(); pygame.event.quit(); pygame.display.quit()
            except Exception:
                pass


class App:
    def __init__(self, root):
        self.root = root
        self.config = carregar_config()
        self.hotspot = HotspotManager(self.config.get("hotspot", {}), log=print)
        self.mcr = None
        self._rcon_lock = threading.Lock()
        self._rcon_fila = queue.Queue(maxsize=300)
        self._encerrando = False
        self._rcon_worker = threading.Thread(target=self._processar_rcon, daemon=True)
        self._rcon_worker.start()
        self._c4_sim_lock = threading.Lock()
        self._c4_simulando = False
        self._c4_grade_visual = None
        self._blocos_cache = {}
        self._tab_cache = {}
        self._binds = []
        self.placar = {"X": 0, "O": 0, "Empate": 0}
        self.c4_placar = {"P1": 0, "P2": 0, "Empate": 0}
        self.jogo_atual = "velha"
        self._idle_id = None
        self._ultima_atividade = 0
        self._anim_ids = []
        self.tabuleiro = [None] * 9
        self.jogador_atual = "X"
        self.fim_jogo = False
        self.hover = None
        self.linha_venc = None
        self.c4_grade = None
        self.c4_cols = 7
        self.c4_lins = 6
        self.c4_jogador = "P1"
        self.c4_fim = False
        self.c4_venc = None
        self.c4_pensando = False
        self._c4_animacao_info = None
        self._c4_animando = None
        self.c4_dificuldade = "medio"
        self.estatisticas = {"partidas": 0, "vitorias": 0, "derrotas": 0, "empates": 0}
        self._inicio_partida = time.monotonic()
        self._conn_monitor_id = None
        self._conn_verificando = False
        self._demo_id = None
        self.calc_visor = "0"
        self.calc_anterior = None
        self.calc_operando = False
        self._botao_off_id = None
        self._botao_geracao = 0
        self._temporizadores_blocos = {}
        self._token_partida_velha = 0
        self._token_partida_c4 = 0
        self._sinal_final_velha_aplicado = False
        self._sinal_final_c4_aplicado = False
        self._joycon_fila = queue.Queue(maxsize=1)
        self._joycon_reader = JoyConReader()
        self._joycon_devices = []
        self._joycon_backend = "none"
        self._joycon_error = None
        self._joycon_prev_buttons = {}
        self._joycon_last_move = {0: 0.0, 1: 0.0}
        self._joycon_last_status = ""
        self._joycon_ttt_cell = 4
        self._joycon_ttt_ativo = False
        self._joycon_pointer_xy = None
        self._joycon_gyro_calibrado = False
        self._joycon_gyro_calibrando = False
        self._joycon_calibracao_pontos = {}
        self._joycon_calibracao_ordem = ()
        self._joycon_calibracao_passo = 0
        self._joycon_calibracao_etapa = None
        self._joycon_calibracao_ativa = False
        self._joycon_calibracao_aviso = ""
        self._joycon_calibracao_viu_gyro_ativo = False
        self._joycon_poll_id = None
        self._tab_last_game = "-"
        self._tab_last_winner = "-"
        self._tab_last_move = "-"
        self.frame_atual = None
        self.frame_conteudo = None
        self._fontes_escala = None
        self.fontes = {}
        self.root.title("Minecraft Arcade")
        self._aplicar_tema()
        self._aplicar_tela()
        self.root.bind("<Escape>", lambda e: self.alternar_tela_cheia())
        self.root.bind("<F11>",    lambda e: self.alternar_tela_cheia())
        self._abrir_inicial()
        self._joycon_reader.iniciar()
        self._joycon_poll_id = self.root.after(JOYCON_UI_POLL_MS, self._joycon_tick)
        if self.config.get("hotspot", {}).get("habilitar", False):
            threading.Thread(target=self._iniciar_hotspot_configurado, daemon=True).start()

    def _joycon_atualizar_status(self):
        try:
            label = getattr(self, "lbl_joycon_info", None)
            if not label or not label.winfo_exists():
                return
            if not JOYCON_ENABLED:
                texto = "Joy-Con desativado; teclado e mouse disponíveis"
            elif self._joycon_error:
                texto = self._joycon_error
            elif self._joycon_backend == "pyjoycon":
                gyro = next((d for d in self._joycon_devices if d["index"] == JOYCON_GYRO_DEVICE_INDEX), None)
                if not self._joycon_devices:
                    texto = "Joy-Con não detectado — confira Bluetooth/permissões HID"
                elif JOYCON_GYRO_TTT_ENABLED and gyro is None:
                    texto = "Mira gyro: conecte o Joy-Con direito para usar B e apontar"
                elif self._joycon_calibracao_etapa == "gyro":
                    texto = "Aponte para a casa 4 (centro) no Minecraft e fique imóvel durante a calibração..."
                elif self._joycon_calibracao_etapa == "pontos":
                    alvo = self._joycon_calibracao_ordem[self._joycon_calibracao_passo]
                    texto = (self._joycon_calibracao_aviso or
                             f"Calibração {len(self._joycon_calibracao_pontos)+1}/9: mire na casa {alvo} "
                             f"({self._joycon_descricao_casa(alvo)}) projetada e aperte B")
                elif (JOYCON_GYRO_TTT_ENABLED and self._joycon_calibracao_ativa
                      and self._joycon_gyro_calibrando):
                    texto = "Calibrando giroscópio; mantenha o controle imóvel..."
                elif (JOYCON_GYRO_TTT_ENABLED and self._joycon_gyro_calibrado
                      and len(self._joycon_calibracao_pontos) == 9):
                    texto = "Nove casas calibradas para o projetor; aponte e aperte B"
                elif JOYCON_GYRO_TTT_ENABLED and not self._joycon_gyro_calibrado:
                    texto = "Joy-Con conectado — aponte para o tabuleiro projetado e clique em CALIBRAR 9 CASAS"
                elif JOYCON_GYRO_TTT_ENABLED:
                    texto = "Giroscópio calibrado; clique em CALIBRAR 9 CASAS para mapear o projetor"
                else:
                    nomes = " | ".join(f"P{d['index']+1}: {d['name']}" for d in self._joycon_devices)
                    texto = f"Joy-Con conectado via PyJoyCon: {nomes}"
            elif not self._joycon_devices:
                if pygame is None:
                    texto = "Instale joycon-python hidapi pyglm para gyro ou pygame para analógico"
                else:
                    texto = "Joy-Con não detectado — teclado e mouse continuam disponíveis"
            else:
                nomes = " | ".join(f"P{d['index']+1}: {d['name']}" for d in self._joycon_devices)
                if JOYCON_GYRO_TTT_ENABLED and self._joycon_backend == "pygame":
                    texto = f"Joy-Con via Pygame: {nomes} — gyro: instale joycon-python hidapi pyglm"
                else:
                    texto = f"Joy-Con conectado: {nomes}"
                if JOYCON_DEBUG:
                    detalhes = " | ".join(
                        f"#{d['index']} eixos={','.join(f'{v:+.2f}' for v in d['axes'])} "
                        f"gyro={d.get('gyro', {})} "
                        f"botões={','.join(str(i) for i,b in enumerate(d['buttons']) if b) or '-'}"
                        for d in self._joycon_devices)
                    texto += "\n" + detalhes
            if texto != self._joycon_last_status:
                label.config(text=texto)
                self._joycon_last_status = texto
        except Exception:
            pass

    def _joycon_indice_jogador(self, jogador):
        posicao = 0 if jogador in ("P1", "X") else 1
        return JOYCON_DEVICE_INDEX[posicao]

    def _joycon_controle_atual(self):
        if not self._joycon_devices or not self.frame_conteudo:
            return None, None
        if self.jogo_atual == "c4":
            if self.c4_fim or self.c4_pensando or self._c4_animando is not None:
                return None, None
            if self.c4_modo == "ia" and self.c4_jogador != "P1":
                return None, None
            jogador = self.c4_jogador
        else:
            if self.fim_jogo:
                return None, None
            modo = self.config.get("velha", {}).get("modo", "ia")
            if modo == "ia" and self.jogador_atual != "X":
                return None, None
            jogador = self.jogador_atual
        if (self.jogo_atual == "velha" and self._joycon_backend == "pyjoycon"
                and JOYCON_GYRO_TTT_ENABLED):
            indice = JOYCON_GYRO_DEVICE_INDEX
        else:
            indice = self._joycon_indice_jogador(jogador)
        for controle in self._joycon_devices:
            if controle["index"] == indice:
                return controle, jogador
        return None, jogador

    def _joycon_mov_c4(self, passo):
        if not getattr(self, "canvas_c4", None) or not self.canvas_c4.winfo_exists():
            return
        atual = self._c4_hover_col if self._c4_hover_col is not None else self.c4_cols // 2
        destino = max(0, min(self.c4_cols - 1, atual + passo))
        if destino != self._c4_hover_col:
            self._c4_hover_col = destino
            self._c4_desenhar()

    def _joycon_mov_velha(self, dx, dy):
        if self.fim_jogo:
            return
        atual = self._joycon_ttt_cell if self._joycon_ttt_ativo else 4
        linha, coluna = divmod(atual, 3)
        nova_linha = max(0, min(2, linha + dy))
        nova_coluna = max(0, min(2, coluna + dx))
        destino = nova_linha * 3 + nova_coluna
        self._joycon_ttt_ativo = True
        self._joycon_ttt_cell = destino
        self._velha_set_hover(destino)
        self._velha_desenhar_tudo()

    @staticmethod
    def _joycon_descricao_casa(indice):
        posicoes = ("superior esquerda", "superior centro", "superior direita",
                    "meio esquerda", "centro", "meio direita",
                    "inferior esquerda", "inferior centro", "inferior direita")
        return posicoes[int(indice)]

    def _joycon_classificar_casa(self, pointer):
        """Retorna a casa cujo ponto aprendido está mais próximo da mira atual."""
        pontos = self._joycon_calibracao_pontos
        if len(pontos) != 9:
            return None
        px, py = float(pointer[0]), float(pointer[1])
        escala_x = max(1e-6, max(p[0] for p in pontos.values()) - min(p[0] for p in pontos.values()))
        escala_y = max(1e-6, max(p[1] for p in pontos.values()) - min(p[1] for p in pontos.values()))
        return min(pontos, key=lambda i: ((px-pontos[i][0])/escala_x)**2 +
                   ((py-pontos[i][1])/escala_y)**2)

    def _joycon_mira_gyro(self, pointer):
        """Converte o vetor relativo do gyro em cursor 2D limitado ao tabuleiro."""
        if not getattr(self, "canvas", None) or not self.canvas.winfo_exists():
            return
        try:
            ang_x = math.atan(float(pointer[0]))
            ang_y = math.atan(float(pointer[1]))
        except (TypeError, ValueError, IndexError):
            return
        destino = self._joycon_classificar_casa(pointer)
        if destino is None:
            if JOYCON_GYRO_INVERT_X: ang_x = -ang_x
            if JOYCON_GYRO_INVERT_Y: ang_y = -ang_y
            alcance = math.radians(max(1.0, JOYCON_GYRO_HALF_RANGE_DEG))
            x = max(0.0, min(self.tam - 1.0, self.tam / 2 + ang_x / alcance * self.tam / 2))
            y = max(0.0, min(self.tam - 1.0, self.tam / 2 + ang_y / alcance * self.tam / 2))
            celula = max(1.0, self.tam / 3)
            destino = min(2, int(y / celula)) * 3 + min(2, int(x / celula))
        else:
            celula = self.tam / 3
            x = (destino % 3 + 0.5) * celula
            y = (destino // 3 + 0.5) * celula
        antiga = self._joycon_ttt_cell
        mudou = not self._joycon_ttt_ativo or destino != antiga
        self._joycon_ttt_ativo = True
        self._joycon_ttt_cell = destino
        if mudou:
            if antiga is not None:
                try: self.canvas.itemconfig(f"casa{antiga}", outline=self.c["linha"], width=1)
                except Exception: pass
            try:
                self.canvas.itemconfig(f"casa{destino}", outline=self.c["destaque"],
                                       width=max(3, int(self.tam * 0.012)))
            except Exception: pass
            self._velha_set_hover(destino)
        self._joycon_pointer_xy = (x, y)
        self._velha_desenhar_ponteiro()

    def _velha_desenhar_ponteiro(self):
        ponto = getattr(self, "_joycon_pointer_xy", None)
        if not ponto or not getattr(self, "canvas", None): return
        try:
            x, y = ponto
            r = max(7, self.tam * 0.018)
            cv = self.canvas
            cv.delete("joycon_pointer")
            cv.create_oval(x-r, y-r, x+r, y+r, outline=self.c["destaque"],
                           width=max(2, int(self.tam * 0.006)), tags="joycon_pointer")
            cv.create_line(x-r*1.5, y, x+r*1.5, y, fill=self.c["texto"], width=1,
                           tags="joycon_pointer")
            cv.create_line(x, y-r*1.5, x, y+r*1.5, fill=self.c["texto"], width=1,
                           tags="joycon_pointer")
        except Exception:
            pass

    def _joycon_calibracao_mostrar_alvo(self, casa):
        self._joycon_ttt_cell = int(casa)
        self._joycon_ttt_ativo = True
        cel = self.tam / 3
        self._joycon_pointer_xy = ((casa % 3 + 0.5) * cel, (casa // 3 + 0.5) * cel)
        self._velha_set_hover(casa)
        self._velha_desenhar_tudo()

    def _joycon_calibracao_comecar_pontos(self, pointer):
        try:
            self._joycon_calibracao_pontos = {4: (float(pointer[0]), float(pointer[1]))}
        except (TypeError, ValueError, IndexError):
            self._joycon_calibracao_pontos = {4: (0.0, 0.0)}
        self._joycon_calibracao_ordem = (0, 1, 2, 3, 5, 6, 7, 8)
        self._joycon_calibracao_passo = 0
        self._joycon_calibracao_etapa = "pontos"
        self._joycon_calibracao_aviso = ""
        alvo = self._joycon_calibracao_ordem[0]
        self._joycon_calibracao_mostrar_alvo(alvo)
        self._log_jogo("Casa 4 registrada no centro. Agora aponte para cada alvo projetado e aperte B.", "aviso")

    def _joycon_calibracao_capturar(self, pointer):
        if self._joycon_calibracao_etapa != "pontos":
            return
        alvo = self._joycon_calibracao_ordem[self._joycon_calibracao_passo]
        ponto = (float(pointer[0]), float(pointer[1]))
        for casa, anterior in self._joycon_calibracao_pontos.items():
            if (ponto[0] - anterior[0]) ** 2 + (ponto[1] - anterior[1]) ** 2 < 1e-5:
                self._joycon_calibracao_aviso = (
                    f"Ponto quase igual à casa {casa}; mire melhor em {alvo} e aperte B novamente"
                )
                return
        self._joycon_calibracao_pontos[alvo] = ponto
        self._joycon_calibracao_aviso = ""
        self._joycon_calibracao_passo += 1
        if self._joycon_calibracao_passo < len(self._joycon_calibracao_ordem):
            proximo = self._joycon_calibracao_ordem[self._joycon_calibracao_passo]
            self._joycon_calibracao_mostrar_alvo(proximo)
            self._log_jogo(f"Casa {alvo} registrada; mire agora na casa {proximo}.", "ok")
            return
        self._joycon_calibracao_ativa = False
        self._joycon_calibracao_etapa = None
        self._joycon_calibracao_passo = 0
        self._joycon_calibracao_aviso = ""
        self._joycon_calibracao_mostrar_alvo(4)
        try:
            self.lbl_joycon_info.config(text="Calibração das 9 casas concluída; aponte e aperte B.",
                                        fg=self.c["destaque"])
        except Exception:
            pass
        self._log_jogo("Calibração concluída: nove posições aprendidas do tabuleiro projetado.", "ok")

    def _joycon_calibrar_mira(self):
        if not PYJOYCON_AVAILABLE:
            try: self.lbl_joycon_info.config(text="Instale: python3 -m pip install joycon-python hidapi pyglm")
            except Exception: pass
            return
        if not any(d["index"] == JOYCON_GYRO_DEVICE_INDEX for d in self._joycon_devices):
            try: self.lbl_joycon_info.config(text="Conecte o Joy-Con direito antes de calibrar as 9 casas")
            except Exception: pass
            return
        self._joycon_gyro_calibrado = False
        self._joycon_gyro_calibrando = True
        self._joycon_calibracao_ativa = True
        self._joycon_calibracao_etapa = "gyro"
        self._joycon_calibracao_pontos = {}
        self._joycon_calibracao_ordem = ()
        self._joycon_calibracao_passo = 0
        self._joycon_calibracao_aviso = ""
        self._joycon_calibracao_viu_gyro_ativo = False
        self._joycon_pointer_xy = None
        self._joycon_calibracao_mostrar_alvo(4)
        self._joycon_reader.pedir_calibracao()
        try:
            self.lbl_joycon_info.config(
                text="Aponte à casa 4 (centro) na projeção e fique imóvel por 1,5 s...",
                fg=self.c["aviso"])
        except Exception:
            pass
        self._log_jogo("Iniciando calibração: aponte ao centro do tabuleiro Minecraft projetado e fique imóvel.", "aviso")

    def _joycon_tick(self):
        if self._encerrando:
            return
        snapshot = None
        try:
            while True:
                snapshot = self._joycon_reader.fila.get_nowait()
        except queue.Empty:
            pass
        if snapshot:
            self._joycon_backend = snapshot.get("backend", self._joycon_backend)
            self._joycon_error = snapshot.get("error")
            self._joycon_devices = snapshot.get("devices", [])
            gyro = next((d for d in self._joycon_devices
                         if d["index"] == JOYCON_GYRO_DEVICE_INDEX), None)
            self._joycon_gyro_calibrado = bool(gyro and gyro.get("gyro_calibrado"))
            self._joycon_gyro_calibrando = bool(gyro and gyro.get("gyro_calibrando"))
        gyro = next((d for d in self._joycon_devices
                     if d["index"] == JOYCON_GYRO_DEVICE_INDEX), None)
        if self._joycon_calibracao_etapa == "gyro":
            if self._joycon_gyro_calibrando:
                self._joycon_calibracao_viu_gyro_ativo = True
            elif (self._joycon_calibracao_viu_gyro_ativo and self._joycon_gyro_calibrado
                  and gyro is not None):
                self._joycon_calibracao_comecar_pontos(gyro.get("pointer") or (0.0, 0.0))
        self._joycon_atualizar_status()

        controle, jogador = self._joycon_controle_atual()
        agora = time.monotonic()
        em_modo_mira = (self.jogo_atual == "velha" and self._joycon_backend == "pyjoycon"
                        and JOYCON_GYRO_TTT_ENABLED)
        ativos = {d["index"]: d for d in self._joycon_devices}
        apertou_confirmar = False
        for indice, dispositivo in ativos.items():
            botoes = dispositivo.get("buttons", [])
            anterior = self._joycon_prev_buttons.get(indice, [])
            if em_modo_mira:
                btn_pos = JOYCON_GYRO_CONFIRM_BUTTON if indice == JOYCON_GYRO_DEVICE_INDEX else -1
            else:
                btn_pos = JOYCON_CONFIRM_BUTTON[0 if indice == JOYCON_DEVICE_INDEX[0] else 1]
            atual = bool(botoes[btn_pos]) if 0 <= btn_pos < len(botoes) else False
            antes = bool(anterior[btn_pos]) if 0 <= btn_pos < len(anterior) else False
            if controle is not None and indice == controle["index"] and atual and not antes:
                apertou_confirmar = True
            self._joycon_prev_buttons[indice] = list(botoes)

        if controle is not None:
            idx_jog = 0 if jogador in ("P1", "X") else 1
            eixos = controle.get("axes", [])
            if self.jogo_atual == "c4":
                eixo = JOYCON_C4_AXIS[idx_jog]
                valor = eixos[eixo] if 0 <= eixo < len(eixos) else 0.0
                if JOYCON_C4_INVERT[idx_jog]: valor = -valor
                direcao = 1 if valor >= JOYCON_DEADZONE else (-1 if valor <= -JOYCON_DEADZONE else 0)
                if direcao and (agora - self._joycon_last_move[idx_jog]) * 1000 >= JOYCON_REPEAT_MS:
                    self._joycon_mov_c4(direcao)
                    self._joycon_last_move[idx_jog] = agora
                if apertou_confirmar and self._c4_hover_col is not None:
                    self._c4_jogar_coluna(self._c4_hover_col)
            elif em_modo_mira:
                ponteiro = controle.get("pointer")
                if self._joycon_calibracao_etapa == "pontos":
                    if apertou_confirmar and ponteiro is not None:
                        self._joycon_calibracao_capturar(ponteiro)
                elif (self._joycon_calibracao_etapa is None
                      and not self._joycon_calibracao_ativa
                      and self._joycon_gyro_calibrado
                      and len(self._joycon_calibracao_pontos) == 9
                      and ponteiro is not None):
                    self._joycon_mira_gyro(ponteiro)
                    if apertou_confirmar:
                        self._velha_jogar(self._joycon_ttt_cell)
            else:
                eixo_x, eixo_y = JOYCON_TTT_AXES[idx_jog]
                raw_x = eixos[eixo_x] if 0 <= eixo_x < len(eixos) else 0.0
                raw_y = eixos[eixo_y] if 0 <= eixo_y < len(eixos) else 0.0
                if JOYCON_TTT_SWAP_AXES[idx_jog]: raw_x, raw_y = raw_y, raw_x
                if JOYCON_TTT_INVERT_X[idx_jog]: raw_x = -raw_x
                if JOYCON_TTT_INVERT_Y[idx_jog]: raw_y = -raw_y
                dx = dy = 0
                if max(abs(raw_x), abs(raw_y)) >= JOYCON_DEADZONE:
                    if abs(raw_x) >= abs(raw_y): dx = 1 if raw_x > 0 else -1
                    else: dy = 1 if raw_y > 0 else -1
                if (dx or dy) and (agora - self._joycon_last_move[idx_jog]) * 1000 >= JOYCON_REPEAT_MS:
                    self._joycon_mov_velha(dx, dy)
                    self._joycon_last_move[idx_jog] = agora
                if apertou_confirmar:
                    pos = self._joycon_ttt_cell if self._joycon_ttt_ativo else 4
                    self._velha_jogar(pos)

        self._joycon_poll_id = self.root.after(JOYCON_UI_POLL_MS, self._joycon_tick)

    def _iniciar_hotspot_configurado(self):
        """Cria/reutiliza a rede somente quando habilitar=True no CONFIG_PADRAO."""
        if self.hotspot.ligar():
            self.hotspot.iniciar_monitor()

    def _abrir_inicial(self):
        self._montar_intro()

    @staticmethod
    def _misturar_cores(cor_a, cor_b, proporcao):
        """Mistura duas cores hexadecimais para transições suaves na interface."""
        proporcao = max(0.0, min(1.0, float(proporcao)))
        a = tuple(int(cor_a[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(cor_b[i:i + 2], 16) for i in (1, 3, 5))
        canais = tuple(round(x + (y - x) * proporcao) for x, y in zip(a, b))
        return "#" + "".join(f"{canal:02x}" for canal in canais)

    def _montar_intro(self):
        self.frame_atual = tk.Frame(self.root, bg=self.c["fundo"])
        self.frame_atual.pack(fill="both", expand=True)
        centro = tk.Frame(self.frame_atual, bg=self.c["fundo"])
        centro.place(relx=0.5, rely=0.5, anchor="center")
        self.intro_titulo = tk.Label(centro, text="MINECRAFT ARCADE", font=self._fonte("titulo"),
                                     bg=self.c["fundo"], fg=self.c["destaque"])
        self.intro_titulo.pack(pady=(0, 4))
        self.intro_subtitulo = tk.Label(centro, text="JOGOS • DESAFIO • DIVERSÃO", font=self._fonte("subtitulo"),
                                        bg=self.c["fundo"], fg=self.c["subtexto"])
        self.intro_subtitulo.pack(pady=(0, 28))
        botoes = tk.Frame(centro, bg=self.c["fundo"]); botoes.pack()
        self._botao(botoes, "JOGO DA VELHA", self.c["x"], self.c["fundo"],
                    lambda: self._entrar_jogo("velha"), True).pack(side="left", padx=8, ipadx=18, ipady=10)
        self._botao(botoes, "CONECT 4", self.c["aviso"], self.c["fundo"],
                    lambda: self._entrar_jogo("c4"), True).pack(side="left", padx=8, ipadx=18, ipady=10)
        self._botao(centro, "⚙  CONFIGURAÇÕES", self.c["painel"], self.c["texto"],
                    lambda: self.trocar_tela("config"), True).pack(pady=(18, 0), ipadx=12)
        self.intro_status = tk.Label(centro, text="Escolha um jogo para começar", font=self._fonte("dica"),
                                     bg=self.c["fundo"], fg=self.c["subtexto"])
        self.intro_status.pack(pady=(24, 0))
        self.lbl_joycon_info = tk.Label(centro, text="Procurando controles...",
                                        font=self._fonte("mini"), bg=self.c["fundo"], fg=self.c["subtexto"])
        self.lbl_joycon_info.pack(pady=(10, 0))
        self._intro_animar(0)

    def _intro_animar(self, fase):
        """Pulso lento de cor no título, sem o efeito de piscar entre cores."""
        if not getattr(self, "intro_titulo", None) or not self.intro_titulo.winfo_exists():
            return
        pulso = (1.0 - math.cos((fase % 100) * (2.0 * math.pi / 100.0))) / 2.0
        intensidade = 0.18 + 0.62 * pulso
        cor = self._misturar_cores(self.c["texto"], self.c["destaque"], intensidade)
        self.intro_titulo.config(fg=cor)
        aid = self.root.after(45, lambda: self._intro_animar(fase + 1))
        self._anim_ids.append(aid)

    def _entrar_jogo(self, modo):
        if self.config.get("modo_offline"):
            self.trocar_tela("jogo", modo)
            return
        if not TEM_RCON:
            self.intro_status.config(
                text="RCON não está instalado. Instale com: pip install mcrcon",
                fg=self.c["erro"])
            return
        self.intro_status.config(text="Conectando ao servidor Minecraft...", fg=self.c["aviso"])
        self.root.update_idletasks()
        if not self._garantir_conexao():
            self.intro_status.config(
                text="Sem conexão RCON. Confira servidor, porta, senha e configurações.",
                fg=self.c["erro"])
            return
        usuario_op = self.config.get("usuario_op", "").strip()
        if usuario_op:
            self._rcon_async(f"op {usuario_op}")
        self.trocar_tela("jogo", modo)

    def _garantir_conexao(self):
        if self.config.get("modo_offline") or not TEM_RCON:
            return False
        if self.mcr:
            try:
                with self._rcon_lock:
                    self.mcr.command("list")
                return True
            except Exception:
                self.mcr = None
                self._tab_cache.clear()
        try:
            self.mcr = MCRcon(self.config["host"], self.config["senha"],
                              port=self.config["porta"], timeout=5)
            self.mcr.connect(); self._tab_cache.clear(); return True
        except Exception:
            self.mcr = None; return False

    def _aplicar_tema(self):
        self.c = TEMAS.get(self.config.get("tema"), TEMAS["feira"])
        self.root.configure(bg=self.c["fundo"])

    def _fonte(self, nome):
        escala = float(self.config["tela"].get("escala", 1.0))
        if self._fontes_escala != escala:
            self._fontes_escala = escala
            self.fontes = {}
        if nome not in self.fontes:
            e = escala
            def mk(size, weight="normal", family="Arial"):
                return tkfont.Font(family=family, size=max(8, int(round(size * e))), weight=weight)
            self.fontes = {
                "titulo": mk(30, "bold"), "subtitulo": mk(12), "secao": mk(15, "bold"),
                "label": mk(11), "campo": mk(11), "botao": mk(12, "bold"),
                "status": mk(20, "bold"), "numero": mk(26, "bold"),
                "log": mk(9, family="Courier"), "dica": mk(10), "mini": mk(9, "bold"),
            }
        return self.fontes[nome]

    def _aplicar_tela(self):
        t = self.config["tela"]
        self.root.geometry(f"{int(t['largura'])}x{int(t['altura'])}")
        self.root.attributes("-fullscreen", bool(t["tela_cheia"]))

    def alternar_tela_cheia(self):
        atual = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not atual)
        self.config["tela"]["tela_cheia"] = not atual

    def _limpar_binds(self):
        for seq, fid in self._binds:
            try: self.root.unbind(seq, fid)
            except Exception: pass
        self._binds = []

    def _bind(self, seq, func):
        fid = self.root.bind(seq, func, add="+")
        self._binds.append((seq, fid))

    def trocar_tela(self, tipo, modo=None):
        if self._idle_id:
            try: self.root.after_cancel(self._idle_id)
            except Exception: pass
            self._idle_id = None
        for aid in self._anim_ids:
            try: self.root.after_cancel(aid)
            except Exception: pass
        self._anim_ids.clear()
        self._limpar_binds()
        if self.frame_atual:
            self.frame_atual.pack_forget()
            self.frame_atual.destroy()
            self.frame_atual = None
        self.frame_conteudo = None
        if tipo == "config":
            self._montar_config()
        elif tipo == "intro":
            self._montar_intro()
        else:
            self._montar_jogo(modo or "velha")

    def _painel(self, parent, titulo):
        p = tk.Frame(parent, bg=self.c["painel"], highlightthickness=1,
                     highlightbackground=self.c["linha"], padx=18, pady=14)
        p.pack(fill="both", expand=True)
        tk.Label(p, text=titulo.upper(), font=self._fonte("mini"), bg=self.c["painel"],
                 fg=self.c["subtexto"]).pack(anchor="w", pady=(0, 12))
        return p

    def _linha_campo(self, parent, rotulo, valor, oculto=False, largura=30):
        linha = tk.Frame(parent, bg=self.c["painel"]); linha.pack(fill="x", pady=5)
        if rotulo:
            tk.Label(linha, text=rotulo, font=self._fonte("label"), bg=self.c["painel"],
                     fg=self.c["texto"], width=28, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(valor))
        tk.Entry(linha, textvariable=var, font=self._fonte("campo"), bg=self.c["campo"],
                 fg=self.c["texto"], insertbackground=self.c["texto"], relief="flat",
                 width=largura, show="*" if oculto else "").pack(
                     side="left", fill="x", expand=True, ipady=8, padx=(10, 0))
        return var

    def _linha_check(self, parent, rotulo, valor):
        var = tk.BooleanVar(value=bool(valor))
        tk.Checkbutton(parent, text=rotulo, variable=var, font=self._fonte("label"),
                       bg=self.c["painel"], fg=self.c["texto"], selectcolor=self.c["campo"],
                       activebackground=self.c["painel"], activeforeground=self.c["texto"],
                       relief="flat", anchor="w", cursor="hand2", padx=0).pack(fill="x", pady=5)
        return var

    def _linha_opcoes(self, parent, rotulo, valor, opcoes):
        linha = tk.Frame(parent, bg=self.c["painel"]); linha.pack(fill="x", pady=5)
        tk.Label(linha, text=rotulo, font=self._fonte("label"), bg=self.c["painel"],
                 fg=self.c["texto"], width=28, anchor="w").pack(side="left")
        var = tk.StringVar(value=str(valor))
        m = tk.OptionMenu(linha, var, *opcoes)
        m.config(font=self._fonte("campo"), bg=self.c["campo"], fg=self.c["texto"],
                 activebackground=self.c["casa_hover"], activeforeground=self.c["texto"],
                 relief="flat", highlightthickness=0, cursor="hand2", width=18)
        m["menu"].config(bg=self.c["campo"], fg=self.c["texto"], font=self._fonte("campo"))
        m.pack(side="left", fill="x", expand=True, padx=(10, 0))
        return var

    def _campo_pequeno(self, parent, valor):
        var = tk.StringVar(value=str(valor))
        tk.Entry(parent, textvariable=var, font=self._fonte("campo"), bg=self.c["campo"],
                 fg=self.c["texto"], insertbackground=self.c["texto"], relief="flat",
                 width=6, justify="center").pack(side="left", padx=3, ipady=6)
        return var

    def _botao(self, parent, texto, bg, fg, comando, compacto=False):
        b = tk.Button(parent, text=texto,
                      font=self._fonte("mini" if compacto else "botao"),
                      bg=bg, fg=fg, activebackground=self.c["casa_hover"],
                      activeforeground=fg, relief="flat", borderwidth=0,
                      cursor="hand2", command=comando,
                      padx=14 if compacto else 20, pady=8 if compacto else 11)
        b.bind("<Enter>", lambda e: b.config(bg=self.c["casa_hover"]))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _log_widget(self, parent, altura=2):
        w = tk.Text(parent, height=altura, font=self._fonte("log"), bg=self.c["painel"],
                    fg=self.c["subtexto"], relief="flat", state="disabled", wrap="word")
        w.tag_config("hora", foreground=self.c["subtexto"])
        w.tag_config("normal", foreground=self.c["texto"])
        w.tag_config("erro", foreground=self.c["erro"])
        w.tag_config("ok", foreground=self.c["destaque"])
        w.tag_config("aviso", foreground=self.c["aviso"])
        return w

    def _escrever(self, widget, msg, tag=None):
        if widget is None: return
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        widget.config(state="normal")
        widget.insert("end", f"[{hora}] ", "hora")
        widget.insert("end", msg + "\n", tag or "normal")
        try:
            total = int(widget.index("end-1c").split(".")[0])
            maxl = int(self.config.get("console", {}).get("historico_max", 200))
            if total > maxl:
                widget.delete("1.0", f"{total - maxl}.0")
        except Exception:
            pass
        widget.see("end")
        widget.config(state="disabled")

    def _rcon(self, comando, silencioso=False):
        if self.config.get("modo_offline") or not self.mcr:
            return None
        try:
            with self._rcon_lock:
                return self.mcr.command(comando)
        except Exception as e:
            if not silencioso:
                self._log_jogo(f"RCON falhou em '{comando[:40]}...': {e}", "erro")
            return None

    def _processar_rcon(self):
        while True:
            comando = self._rcon_fila.get()
            try:
                if comando is None:
                    return
                enviado = False
                for tentativa in range(3):
                    if self._rcon(comando, silencioso=True) is not None:
                        enviado = True
                        break
                    if tentativa < 2 and not self.config.get("modo_offline"):
                        time.sleep(0.15)
                        self._garantir_conexao()
                if not enviado and not self._encerrando:
                    try:
                        self.root.after(0, lambda cmd=comando: self._log_jogo(
                            f"RCON não confirmou o comando: {cmd[:55]}", "erro"))
                    except Exception:
                        pass
            finally:
                self._rcon_fila.task_done()

    def _rcon_async(self, comando):
        if self._encerrando or self.config.get("modo_offline") or not TEM_RCON:
            return False
        try:
            self._rcon_fila.put_nowait(str(comando))
            return True
        except queue.Full:
            try:
                self.root.after(0, lambda: self._log_jogo(
                    "Fila RCON cheia; esta jogada não foi enviada ao Minecraft.", "erro"))
            except Exception:
                pass
            return False

    def _rcon_setblock(self, x, y, z, bloco, silencioso=False, forcar=False, assincrono=False):
        """Evita enviar setblock repetido quando o estado conhecido não mudou."""
        try:
            pos = (int(x), int(y), int(z))
        except Exception:
            return None
        bloco = str(bloco).strip()
        if not bloco:
            return None
        if not forcar and self._blocos_cache.get(pos) == bloco:
            return True
        comando = f"setblock {pos[0]} {pos[1]} {pos[2]} {bloco}"
        if assincrono:
            enfileirado = self._rcon_async(comando)
            if enfileirado:
                self._blocos_cache[pos] = bloco
            return enfileirado
        resultado = self._rcon(comando, silencioso=silencioso)
        if resultado is not None:
            self._blocos_cache[pos] = bloco
        return resultado

    def _tab_update(self):
        """Publica o estado atual no ArcadeTabBridge para o TAB/PlaceholderAPI."""
        if self.config.get("modo_offline") or not self.mcr:
            return
        try:
            if self.jogo_atual == "c4":
                jogo = "Conect_4"
                atual = "P1" if self.c4_jogador == "P1" else "P2"
                fim = self.c4_fim
                score_c4 = f"P1_{self.c4_placar.get('P1', 0)}_P2_{self.c4_placar.get('P2', 0)}_Empates_{self.c4_placar.get('Empate', 0)}"
            else:
                jogo = "Jogo_da_Velha"
                atual = self.jogador_atual
                fim = self.fim_jogo
                score_c4 = f"P1_{self.c4_placar.get('P1', 0)}_P2_{self.c4_placar.get('P2', 0)}_Empates_{self.c4_placar.get('Empate', 0)}"
            status = "Fim_de_jogo" if fim else f"Vez_de_{atual}"
            score_velha = f"X_{self.placar.get('X', 0)}_O_{self.placar.get('O', 0)}_Empates_{self.placar.get('Empate', 0)}"
            dados = {
                "game": jogo,
                "current_player": "Fim" if fim else atual,
                "status": status,
                "last_game": self._tab_last_game,
                "last_winner": self._tab_last_winner,
                "last_move": self._tab_last_move,
                "score_velha": score_velha,
                "score_c4": score_c4,
            }
            for key, value in dados.items():
                self._tab_set(key, value)
        except Exception:
            pass

    def _dino_evento(self, jogo, resultado):
        """Atualiza a reação do dinossauro apenas com status do TAB."""
        dificuldade = self._dificuldade_do_jogo(jogo)
        dino = DINOSSAUROS_DIFICULDADE[dificuldade]
        self._tab_set("dino", dino["nome"])
        self._tab_set("dino_cor", dino["cor"])
        mapa = {"move": "jogada", "thinking": "pensando", "draw": "empate"}
        self._tab_set("dino_reacao", mapa.get(resultado, "feliz" if "win" in resultado else "triste" if "lose" in resultado else resultado))

    def _dificuldade_do_jogo(self, jogo):
        if jogo == "velha":
            valor = self.config.get("velha", {}).get("dificuldade", "dificil")
        else:
            valor = self.config.get("conect4", {}).get("dificuldade", getattr(self, "c4_dificuldade", "medio"))
        valor = str(valor).lower().strip()
        return valor if valor in DINOSSAUROS_DIFICULDADE else "dificil"

    def _tab_set(self, chave, valor):
        safe = str(valor).replace(" ", "_").replace('"', '')
        if self._tab_cache.get(chave) == safe:
            return
        self._tab_cache[chave] = safe
        self._rcon_async(f"arcadetab set {chave} {safe}")

    def _dino_inicio(self, jogo):
        dificuldade = self._dificuldade_do_jogo(jogo)
        dino = DINOSSAUROS_DIFICULDADE[dificuldade]
        self._tab_set("dino", dino["nome"])
        self._tab_set("dino_cor", dino["cor"])

    def _modo_botao_ativo(self):
        return bool(self.config.get("controles_minecraft", {}).get("modo_botao", True))

    def _texto_modo_botao(self):
        return "BOTÃO: ON" if self._modo_botao_ativo() else "BOTÃO: OFF"

    def _alternar_modo_botao(self):
        cfg = self.config.setdefault("controles_minecraft", copy.deepcopy(CONFIG_PADRAO["controles_minecraft"]))
        cfg["modo_botao"] = not bool(cfg.get("modo_botao", True))
        if getattr(self, "btn_modo_botao", None):
            self.btn_modo_botao.config(text=self._texto_modo_botao())
        try:
            salvar_config(self.config)
        except Exception:
            pass
        self._log_jogo("Modo botão " + ("ativado." if cfg["modo_botao"] else "desativado."), "aviso")

    def _intervalo_min_jogadas_ms(self):
        try:
            return max(0, int(self.config.get("controles_minecraft", {}).get("intervalo_min_jogadas_ms", 1000)))
        except Exception:
            return 450

    def _texto_intervalo(self):
        return f"INTERVALO: {self._intervalo_min_jogadas_ms() / 1000:.1f}s"

    def _aumentar_intervalo(self):
        cfg = self.config.setdefault("controles_minecraft", copy.deepcopy(CONFIG_PADRAO["controles_minecraft"]))
        cfg["intervalo_min_jogadas_ms"] = min(30000, self._intervalo_min_jogadas_ms() + 500)
        if getattr(self, "btn_intervalo", None):
            self.btn_intervalo.config(text=self._texto_intervalo())
        try:
            salvar_config(self.config)
        except Exception:
            pass
        self._log_jogo(f"Intervalo mínimo: {self._texto_intervalo()}", "aviso")

    def _pode_jogar_agora(self):
        agora = time.monotonic()
        ultimo = getattr(self, "_ultima_jogada_monotonic", 0.0)
        if agora - ultimo < self._intervalo_min_jogadas_ms() / 1000:
            return False
        self._ultima_jogada_monotonic = agora
        return True

    def _pulso_modo_botao(self, coord, terracota, chave):
        """Coloca terracota acima da coordenada, pulsa redstone e remove só a redstone."""
        try:
            x, y, z = (int(v) for v in coord)
            cfg = self.config.get("controles_minecraft", {})
            redstone = cfg.get("bloco_ligado", "redstone_block")
            desligado = cfg.get("bloco_desligado", "air")
            self._rcon_setblock(x, y + 1, z, terracota, silencioso=True, forcar=True, assincrono=True)
            self._rcon_setblock(x, y, z, redstone, silencioso=True, forcar=True, assincrono=True)
            anterior = self._temporizadores_blocos.pop(("botao", chave), None)
            if anterior:
                try:
                    self.root.after_cancel(anterior)
                except Exception:
                    pass
            duracao = max(100, int(cfg.get("duracao_reset_ms", 2000)))
            self._temporizadores_blocos[("botao", chave)] = self.root.after(
                duracao, lambda: self._finalizar_pulso_botao(("botao", chave), (x, y, z), desligado))
        except Exception as e:
            self._log_jogo(f"Modo botão falhou: {e}", "erro")

    def _finalizar_pulso_botao(self, chave, coord, desligado):
        self._temporizadores_blocos.pop(chave, None)
        self._rcon_setblock(*coord, desligado, silencioso=True, forcar=True, assincrono=True)

    def _invalidar_cache_blocos(self):
        self._blocos_cache.clear()

    def _cancelar_temporizador_bloco(self, chave):
        aid = self._temporizadores_blocos.pop(chave, None)
        if aid:
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass

    # ============================================================
    # CONFIGURAÇÕES
    # ============================================================
    def _montar_config(self):
        self.frame_atual = tk.Frame(self.root, bg=self.c["fundo"])
        self.frame_atual.pack(fill="both", expand=True)

        topo = tk.Frame(self.frame_atual, bg=self.c["fundo"])
        topo.pack(fill="x", padx=36, pady=(24, 16))
        tk.Label(topo, text="Configurações", font=self._fonte("titulo"),
                 bg=self.c["fundo"], fg=self.c["texto"]).pack(side="left")
        self._botao(topo, "← VOLTAR À ESCOLHA", self.c["painel"], self.c["texto"],
                    self._voltar_intro, True).pack(side="right", padx=(8, 0))
        tk.Label(topo, text="● PRONTO", font=self._fonte("mini"),
                 bg=self.c["fundo"], fg=self.c["destaque"]).pack(side="right")

        corpo = tk.Frame(self.frame_atual, bg=self.c["fundo"])
        corpo.pack(fill="both", expand=True, padx=36)
        nav = tk.Frame(corpo, bg=self.c["fundo"], width=190)
        nav.pack(side="left", fill="y", padx=(0, 18)); nav.pack_propagate(False)
        area = tk.Frame(corpo, bg=self.c["fundo"])
        area.pack(side="left", fill="both", expand=True)

        self.paginas = {}
        self.nav_botoes = {}
        for nome in ("Conexão", "Minecraft", "Coordenadas", "Tela", "Console", "Conect 4", "Controles Minecraft", "Hotspot"):
            pg = tk.Frame(area, bg=self.c["fundo"])
            self.paginas[nome] = pg
            b = self._botao(nav, nome, self.c["painel"], self.c["texto"],
                            lambda n=nome: self._mostrar_pagina(n))
            b.pack(fill="x", pady=(0, 6)); self.nav_botoes[nome] = b

        self._pagina_conexao()
        self._pagina_minecraft()
        self._pagina_coordenadas()
        self._pagina_tela()
        self._pagina_console()
        self._pagina_c4()
        self._pagina_controles_minecraft()
        self._pagina_hotspot()

        rod = tk.Frame(self.frame_atual, bg=self.c["fundo"])
        rod.pack(fill="x", padx=36, pady=(14, 24))
        self.log_config = self._log_widget(rod, 2)
        self.log_config.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self._botao(rod, "Testar",  self.c["painel"],    self.c["texto"], self._testar_conexao, True).pack(side="left", padx=4)
        self._botao(rod, "Padrão",  self.c["painel"],    self.c["aviso"], self._restaurar_padrao, True).pack(side="left", padx=4)
        self._botao(rod, "Salvar",  self.c["campo"],     self.c["texto"], self._salvar, True).pack(side="left", padx=4)
        self._botao(rod, "Voltar", self.c["painel"],    self.c["texto"], self._voltar_intro, True).pack(side="left", padx=4)
        self._botao(rod, "INICIAR", self.c["destaque"],  self.c["fundo"], lambda: self._iniciar("velha")).pack(side="left", padx=(8, 0))

        self._mostrar_pagina("Conexão")


    def _voltar_intro(self):
        try:
            self._salvar()
        except Exception:
            pass
        self.trocar_tela("intro")

    def _mostrar_pagina(self, nome):
        for pg in self.paginas.values(): pg.pack_forget()
        self.paginas[nome].pack(fill="both", expand=True)
        for k, b in self.nav_botoes.items():
            b.config(bg=self.c["campo"] if k == nome else self.c["painel"], fg=self.c["texto"])

    def _log_config(self, msg, tag=None):
        self._escrever(getattr(self, "log_config", None), msg, tag)

    def _pagina_conexao(self):
        p = self._painel(self.paginas["Conexão"], "Conexão RCON")
        cfg = self.config
        self.var_host    = self._linha_campo(p, "Host", cfg["host"])
        self.var_porta   = self._linha_campo(p, "Porta", cfg["porta"])
        self.var_senha   = self._linha_campo(p, "Senha", cfg["senha"], oculto=True)
        self.var_usuario = self._linha_campo(p, "Usuário OP (opcional)", cfg["usuario_op"])
        self.var_offline = self._linha_check(p, "Modo offline (sem servidor)", cfg["modo_offline"])
        if not TEM_RCON:
            tk.Label(p, text="RCON não instalado. Modo offline obrigatório.",
                     font=self._fonte("dica"), bg=self.c["painel"],
                     fg=self.c["aviso"]).pack(anchor="w", pady=(8, 0))

    def _pagina_hotspot(self):
        p = self._painel(self.paginas["Hotspot"], "Hotspot da rede local")
        h = self.config.setdefault("hotspot", copy.deepcopy(CONFIG_PADRAO["hotspot"]))
        tk.Label(p, text="A rede só será criada quando Habilitar estiver marcado. Se o nome/IP estiverem ocupados, será usado o nome backup.",
                 font=self._fonte("dica"), bg=self.c["painel"], fg=self.c["subtexto"],
                 wraplength=900, justify="left").pack(anchor="w", pady=(0, 12))
        self.var_hotspot_habilitar = self._linha_check(p, "Habilitar hotspot ao iniciar", h.get("habilitar", False))
        self.var_hotspot_nome = self._linha_campo(p, "Nome da rede", h.get("nome", "PORTA ZERO"))
        self.var_hotspot_senha = self._linha_campo(p, "Senha", h.get("senha", "portazero0"), oculto=True)
        self.var_hotspot_ip = self._linha_campo(p, "IP do hotspot", h.get("ip", "10.0.1.13/24"))
        self.var_hotspot_backup = self._linha_campo(p, "Nome de backup", h.get("nome_backup", "PORTA ZERO backup"))
        self.var_hotspot_desligar = self._linha_check(p, "Desligar sem internet e religar quando voltar", h.get("desligar_sem_internet", True))
        self.var_hotspot_intervalo = self._linha_campo(p, "Verificar internet a cada segundos", h.get("verificar_a_cada_segundos", 15), largura=10)
        self.var_hotspot_interface = self._linha_campo(p, "Interface Wi-Fi (opcional)", h.get("interface", ""))

    def _pagina_minecraft(self):
        p = self._painel(self.paginas["Minecraft"], "Jogadores e blocos")
        cfg = self.config
        self.var_nome_x     = self._linha_campo(p, "Nome do jogador (humano)", cfg["nomes"]["X"])
        self.var_nome_o     = self._linha_campo(p, "Nome do oponente (IA)", cfg["nomes"]["O"])
        self.var_bloco_base = self._linha_campo(p, "Bloco da base", cfg["bloco_base"])
        self.var_bloco_x    = self._linha_campo(p, "Bloco do humano", cfg["bloco_x"])
        self.var_bloco_o    = self._linha_campo(p, "Bloco do oponente", cfg["bloco_o"])

    def _pagina_coordenadas(self):
        p = self._painel(self.paginas["Coordenadas"], "Coordenadas — Jogo da Velha")
        tk.Label(p, text="X, Y, Z — esquerda→direita, cima→baixo",
                 font=self._fonte("dica"), bg=self.c["painel"],
                 fg=self.c["subtexto"]).pack(anchor="w", pady=(0, 10))
        grade = tk.Frame(p, bg=self.c["painel"]); grade.pack(anchor="w")
        self.campos_coord = {}
        for i in range(9):
            x, y, z = self.config["coordenadas"][str(i)]
            cell = tk.Frame(grade, bg=self.c["campo"], padx=9, pady=9)
            cell.grid(row=i//3, column=i%3, padx=4, pady=4)
            cab = tk.Frame(cell, bg=self.c["campo"]); cab.pack(fill="x", pady=(0, 3))
            tk.Label(cab, text=f"Casa {i}", font=self._fonte("mini"),
                     bg=self.c["campo"], fg=self.c["subtexto"]).pack(side="left")
            self._botao(cab, "↺", self.c["campo"], self.c["subtexto"],
                        lambda idx=i: self._restaurar_casa(idx), True).pack(side="right")
            row = tk.Frame(cell, bg=self.c["campo"]); row.pack()
            self.campos_coord[i] = (
                self._campo_pequeno(row, x),
                self._campo_pequeno(row, y),
                self._campo_pequeno(row, z))

        gen = tk.Frame(p, bg=self.c["painel"]); gen.pack(fill="x", pady=(14, 0))
        tk.Label(gen, text="Passo", font=self._fonte("dica"),
                 bg=self.c["painel"], fg=self.c["subtexto"]).pack(side="left")
        self.var_passo = self._campo_pequeno(gen, 4)
        self.var_eixo_col = tk.StringVar(value="X")
        self.var_eixo_lin = tk.StringVar(value="Z")
        self.var_dir_h    = tk.StringVar(value="+1")
        self.var_dir_v    = tk.StringVar(value="+1")
        for label, var, opts in (("Eixo col", self.var_eixo_col, ("X","Z")),
                                  ("Eixo lin", self.var_eixo_lin, ("X","Z")),
                                  ("Dir H", self.var_dir_h, ("+1","-1")),
                                  ("Dir V", self.var_dir_v, ("+1","-1"))):
            tk.Label(gen, text=label, font=self._fonte("dica"),
                     bg=self.c["painel"], fg=self.c["subtexto"]).pack(side="left", padx=(12,3))
            tk.OptionMenu(gen, var, *opts).pack(side="left")
        self._botao(gen, "Gerar grade", self.c["campo"], self.c["texto"],
                    self._gerar_grade_velha, True).pack(side="left", padx=12)

    def _escolher_pasta_config(self):
        self._log_config("A configuração padrão está embutida no main.py; não há arquivo externo.", "aviso")
        return
        global PASTA_CONFIG, CAMINHO_CONFIG
        atual = PASTA_CONFIG if os.path.isdir(PASTA_CONFIG) else PASTA_APLICATIVO
        pasta = filedialog.askdirectory(
            parent=self.root,
            title="Escolha a pasta para guardar os arquivos de configuração",
            initialdir=atual,
            mustexist=False,
        )
        if not pasta:
            return
        pasta = os.path.abspath(os.path.expanduser(pasta))
        try:
            os.makedirs(pasta, exist_ok=True)
            arquivo_antigo = CAMINHO_CONFIG
            novo_caminho = os.path.join(pasta, "config.json")
            if os.path.abspath(novo_caminho) != os.path.abspath(arquivo_antigo):
                if os.path.exists(arquivo_antigo) and not os.path.exists(novo_caminho):
                    shutil.copy2(arquivo_antigo, novo_caminho)
                elif not os.path.exists(novo_caminho):
                    with open(novo_caminho, "w", encoding="utf-8") as f:
                        json.dump(self.config, f, indent=2, ensure_ascii=False)
            PASTA_CONFIG = pasta
            CAMINHO_CONFIG = novo_caminho
            with open(ARQUIVO_PASTA_CONFIG, "w", encoding="utf-8") as f:
                f.write(PASTA_CONFIG)
            self.config = carregar_config()
            if getattr(self, "var_pasta_config", None):
                self.var_pasta_config.set(PASTA_CONFIG)
            self._aplicar_tema()
            self._aplicar_tela()
            self._log_config(f"Pasta de configurações: {PASTA_CONFIG}", "ok")
        except Exception as e:
            self._log_config(f"Não foi possível usar a pasta escolhida: {e}", "erro")

    def _pagina_tela(self):
        p = self._painel(self.paginas["Tela"], "Exibição e modo feira")
        t = self.config["tela"]
        self.var_tela_cheia  = self._linha_check(p, "Iniciar em tela cheia", t["tela_cheia"])
        self.var_modo_feira  = self._linha_check(p, "Modo feira (reinicia por inatividade)", t["modo_feira"])
        self.var_modo_demo   = self._linha_check(p, "Modo demonstração automática", t.get("modo_demo", False))
        self.var_resolucao   = self._linha_opcoes(p, "Resolução",
                                                  f"{int(t['largura'])}x{int(t['altura'])}",
                                                  ["1280x720","1366x768","1600x900","1920x1080","2560x1440"])
        self.var_escala      = self._linha_opcoes(p, "Escala", f"{t['escala']:.2f}",
                                                  ["0.75","0.90","1.00","1.15","1.30","1.50"])
        self.var_tabuleiro   = self._linha_campo(p, "Tamanho do tabuleiro", int(t["tamanho_tabuleiro"]), largura=10)
        self.var_mostrar_simbolos = self._linha_check(p, "Mostrar X e O / peças na tela", t.get("mostrar_simbolos", True))
        self.var_mostrar_log = self._linha_check(p, "Mostrar painel de eventos", t["mostrar_log"])
        self.var_largura_log = self._linha_campo(p, "Largura do painel de eventos", int(t["largura_log"]), largura=10)
        self.var_inatividade = self._linha_campo(p, "Inatividade (segundos)", int(t["inatividade_segundos"]), largura=10)
        self.var_tema        = self._linha_opcoes(p, "Aparência", self.config["tema"], list(TEMAS.keys()))

        cfgrow = tk.Frame(p, bg=self.c["painel"])
        cfgrow.pack(fill="x", pady=(10, 4))
        tk.Label(cfgrow, text="Pasta dos configs", font=self._fonte("dica"),
                 bg=self.c["painel"], fg=self.c["subtexto"]).pack(side="left")
        self.var_pasta_config = tk.StringVar(value=PASTA_CONFIG)
        ent = tk.Entry(cfgrow, textvariable=self.var_pasta_config,
                       font=self._fonte("campo"), bg=self.c["campo"], fg=self.c["texto"],
                       insertbackground=self.c["texto"], relief="flat")
        ent.pack(side="left", fill="x", expand=True, padx=(10, 8), ipady=5)
        self._botao(cfgrow, "Escolher pasta...", self.c["campo"], self.c["texto"],
                    self._escolher_pasta_config, True).pack(side="left")
        tk.Label(p, text="O programa guarda o config.json dentro dessa pasta.",
                 font=self._fonte("mini"), bg=self.c["painel"], fg=self.c["subtexto"]).pack(anchor="w", pady=(2, 0))

    def _pagina_console(self):
        p = self._painel(self.paginas["Console"], "Console RCON")
        self.txt_console = tk.Text(p, height=14, font=self._fonte("log"), bg=self.c["campo"],
                                   fg=self.c["texto"], relief="flat", wrap="word", state="disabled")
        self.txt_console.tag_config("entrada", foreground=self.c["destaque"])
        self.txt_console.tag_config("resposta", foreground=self.c["texto"])
        self.txt_console.tag_config("erro", foreground=self.c["erro"])
        self.txt_console.tag_config("hora", foreground=self.c["subtexto"])
        self.txt_console.pack(fill="both", expand=True)

        linha = tk.Frame(p, bg=self.c["painel"]); linha.pack(fill="x", pady=(10, 0))
        self.entry_cmd = tk.Entry(linha, font=self._fonte("campo"), bg=self.c["campo"],
                                  fg=self.c["texto"], insertbackground=self.c["texto"], relief="flat")
        self.entry_cmd.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry_cmd.bind("<Return>", lambda e: self._enviar_cmd())
        self._botao(linha, "Enviar", self.c["destaque"], self.c["fundo"],
                    self._enviar_cmd, True).pack(side="left", padx=(8, 0))

        rap = tk.Frame(p, bg=self.c["painel"]); rap.pack(fill="x", pady=(8, 0))
        for cmd in ("say Olá!", "time set day", "weather clear", "list"):
            self._botao(rap, cmd, self.c["campo"], self.c["texto"],
                        lambda c=cmd: self._enviar_cmd(c), True).pack(side="left", padx=3)
        self._botao(rap, "Limpar", self.c["campo"], self.c["erro"],
                    self._limpar_console, True).pack(side="right")

        if not self.config["modo_offline"] and TEM_RCON:
            if self._garantir_conexao():
                self._log_console(f"Conectado a {self.config['host']}:{self.config['porta']}", "resposta")
            else:
                self._log_console("Sem conexão. Ative o modo offline ou teste.", "erro")
        else:
            self._log_console("Modo offline ativo.", "erro")

    def _pagina_controles_minecraft(self):
        p = self._painel(self.paginas["Controles Minecraft"], "Controles Minecraft")
        cfg = self.config.setdefault("controles_minecraft", copy.deepcopy(CONFIG_PADRAO["controles_minecraft"]))
        tk.Label(p, text="RESET: somente Novo Jogo pulsa por 2 segundos. JOGADOR: X/P1 liga e O/P2 desliga permanentemente.",
                 font=self._fonte("dica"), bg=self.c["painel"], fg=self.c["subtexto"],
                 wraplength=900, justify="left").pack(anchor="w", pady=(0, 12))
        self.controle_vars = {}
        for chave, titulo in (("velha", "Jogo da Velha"), ("conect4", "Conect 4")):
            box = tk.Frame(p, bg=self.c["campo"], padx=12, pady=10)
            box.pack(fill="x", pady=5)
            tk.Label(box, text=titulo, font=self._fonte("secao"), bg=self.c["campo"], fg=self.c["texto"]).pack(anchor="w")
            row = tk.Frame(box, bg=self.c["campo"]); row.pack(fill="x", pady=(8, 0))
            tk.Label(row, text="Reset X,Y,Z", font=self._fonte("dica"), bg=self.c["campo"], fg=self.c["subtexto"]).pack(side="left")
            rv = tuple(self._campo_pequeno(row, v) for v in cfg.get(chave, {}).get("reset", [0, 70, 0]))
            tk.Label(row, text="   Jogador X,Y,Z", font=self._fonte("dica"), bg=self.c["campo"], fg=self.c["subtexto"]).pack(side="left")
            jv = tuple(self._campo_pequeno(row, v) for v in cfg.get(chave, {}).get("jogador", [0, 70, 0]))
            self.controle_vars[chave] = {"reset": rv, "jogador": jv}
        row = tk.Frame(p, bg=self.c["painel"]); row.pack(fill="x", pady=(12, 0))
        self.var_controle_on = self._linha_campo(row, "Bloco ligado", cfg.get("bloco_ligado", "redstone_block"), largura=16)
        self.var_controle_off = self._linha_campo(row, "Bloco desligado", cfg.get("bloco_desligado", "air"), largura=12)
        self.var_controle_duracao = self._linha_campo(row, "Duração reset (ms)", cfg.get("duracao_reset_ms", 2000), largura=10)
        self.var_intervalo_min = self._linha_campo(p, "Intervalo mínimo entre jogadas (ms)", cfg.get("intervalo_min_jogadas_ms", 1000), largura=10)
        self.var_controle_modo_botao = self._linha_check(p, "Modo botão nos dois jogos", cfg.get("modo_botao", True))

    def _pagina_c4(self):
        p = self._painel(self.paginas["Conect 4"], "Conect 4 — 7 saídas em linha")
        c4 = self.config["conect4"]
        tk.Label(p, text="Uma coordenada X,Y,Z para cada coluna (1 a 7). X/P1 liga redstone; O/P2 desliga.",
                 font=self._fonte("dica"), bg=self.c["painel"], fg=self.c["subtexto"]).pack(anchor="w", pady=(0, 8))
        grade = tk.Frame(p, bg=self.c["painel"]); grade.pack(anchor="w")
        self.campos_c4_colunas = {}
        coords = c4.get("coordenadas_colunas", {})
        for i in range(7):
            cell = tk.Frame(grade, bg=self.c["campo"], padx=7, pady=7)
            cell.grid(row=0, column=i, padx=3)
            tk.Label(cell, text=f"Coluna {i+1}", font=self._fonte("mini"), bg=self.c["campo"], fg=self.c["subtexto"]).pack()
            coord = coords.get(str(i), [i * 2, 70, 0])
            row = tk.Frame(cell, bg=self.c["campo"]); row.pack()
            self.campos_c4_colunas[i] = tuple(self._campo_pequeno(row, v) for v in coord)

        l2 = tk.Frame(p, bg=self.c["painel"]); l2.pack(fill="x", pady=5)
        tk.Label(l2, text="Linhas do jogo", font=self._fonte("dica"), bg=self.c["painel"], fg=self.c["subtexto"]).pack(side="left")
        self.var_c4_lins = self._campo_pequeno(l2, c4.get("linhas", 6))
        tk.Label(l2, text="  Dificuldade", font=self._fonte("dica"), bg=self.c["painel"], fg=self.c["subtexto"]).pack(side="left")
        self.var_c4_dif = tk.StringVar(value=c4.get("dificuldade", "medio"))
        m = tk.OptionMenu(l2, self.var_c4_dif, "facil", "medio", "dificil", "impossivel")
        m.config(font=self._fonte("campo"), bg=self.c["campo"], fg=self.c["texto"], relief="flat", highlightthickness=0, width=12)
        m["menu"].config(bg=self.c["campo"], fg=self.c["texto"]); m.pack(side="left", padx=(8, 0))

        ac = tk.Frame(p, bg=self.c["painel"]); ac.pack(fill="x", pady=(12, 0))
        self._botao(ac, "▶ JOGAR", self.c["destaque"], self.c["fundo"], lambda: self._iniciar("c4")).pack(side="left", padx=3)
        self.lbl_preview_c4 = tk.Label(p, text="7 saídas em linha.", font=self._fonte("log"), bg=self.c["painel"], fg=self.c["subtexto"], anchor="w", justify="left")
        self.lbl_preview_c4.pack(fill="x", pady=(10, 0))
        self._atualizar_preview_c4()

    # ---------- ações das configs ----------
    def _restaurar_casa(self, i):
        x, y, z = CONFIG_PADRAO["coordenadas"][str(i)]
        ex, ey, ez = self.campos_coord[i]
        ex.set(x); ey.set(y); ez.set(z)

    def _gerar_grade_velha(self):
        try:
            x0, y0, z0 = (int(v.get()) for v in self.campos_coord[0])
            passo = int(self.var_passo.get())
            if passo < 1: raise ValueError
        except ValueError:
            self._log_config("Casa 0 e passo precisam ser inteiros >= 1.", "erro"); return
        ecol, elin = self.var_eixo_col.get(), self.var_eixo_lin.get()
        if ecol == elin:
            self._log_config("Eixos não podem ser iguais.", "erro"); return
        dh = int(self.var_dir_h.get()); dv = int(self.var_dir_v.get())
        for i in range(9):
            col, lin = i % 3, i // 3
            x, y, z = x0, y0, z0
            if ecol == "X": x += col * passo * dh
            else:           z += col * passo * dh
            if elin == "Z": z += lin * passo * dv
            else:           x += lin * passo * dv
            ex, ey, ez = self.campos_coord[i]
            ex.set(x); ey.set(y0); ez.set(z)
        self._log_config("Grade do Jogo da Velha gerada.", "ok")

    def _gerar_grade_c4(self):
        try:
            coords = {str(i): [int(v.get()) for v in self.campos_c4_colunas[i]] for i in range(7)}
        except ValueError:
            self._log_config("Conect 4: todas as 7 coordenadas precisam ser inteiras.", "erro"); return
        self.config["conect4"]["coordenadas_colunas"] = coords
        self._atualizar_preview_c4()
        self._log_config("Conect 4: 7 coordenadas lineares salvas.", "ok")

    def _atualizar_preview_c4(self):
        if not getattr(self, "lbl_preview_c4", None): return
        coords = self.config["conect4"].get("coordenadas_colunas", {})
        txt = "  ".join(f"{int(k)+1}->{v}" for k, v in coords.items())
        self.lbl_preview_c4.config(text=f"7 colunas: {txt}")

    def _log_console(self, msg, tag="resposta"):
        w = getattr(self, "txt_console", None)
        if not w: return
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        w.config(state="normal")
        w.insert("end", f"[{hora}] ", "hora")
        w.insert("end", msg + "\n", tag)
        try:
            total = int(w.index("end-1c").split(".")[0])
            if total > 200: w.delete("1.0", f"{total-200}.0")
        except Exception: pass
        w.see("end")
        w.config(state="disabled")

    def _enviar_cmd(self, cmd=None):
        w = getattr(self, "txt_console", None)
        if not w: return
        cmd = cmd if cmd is not None else self.entry_cmd.get().strip()
        try: self.entry_cmd.delete(0, "end")
        except Exception: pass
        if not cmd: return
        self._log_console(f"> {cmd}", "entrada")
        if self.config["modo_offline"] or not TEM_RCON:
            self._log_console("(offline)", "erro"); return
        if not self._garantir_conexao():
            self._log_console("(sem conexão)", "erro"); return
        try:
            with self._rcon_lock:
                r = self.mcr.command(cmd)
            self._log_console(r or "(vazio)", "resposta")
        except Exception as e:
            self._log_console(f"ERRO: {e}", "erro")

    def _limpar_console(self):
        w = getattr(self, "txt_console", None)
        if not w: return
        w.config(state="normal"); w.delete("1.0", "end"); w.config(state="disabled")

    def _coletar(self):
        coord = {str(i): [int(e.get()), int(ey.get()), int(ez.get())]
                 for i, (e, ey, ez) in self.campos_coord.items()}
        larg, alt = (int(v) for v in self.var_resolucao.get().lower().split("x"))

        c4 = copy.deepcopy(self.config["conect4"])
        try:
            c4.update({
                "coordenadas_colunas": {str(i): [int(v.get()) for v in self.campos_c4_colunas[i]] for i in range(7)},
                "linhas": int(self.var_c4_lins.get()),
                "dificuldade": self.var_c4_dif.get(),
                "modo": self.config.get("conect4", {}).get("modo", "ia"),
            })
        except Exception:
            pass

        controles = copy.deepcopy(self.config.get("controles_minecraft", CONFIG_PADRAO["controles_minecraft"]))
        try:
            for chave in ("velha", "conect4"):
                controles[chave]["reset"] = [int(v.get()) for v in self.controle_vars[chave]["reset"]]
                controles[chave]["jogador"] = [int(v.get()) for v in self.controle_vars[chave]["jogador"]]
            controles["bloco_ligado"] = self.var_controle_on.get().strip() or "redstone_block"
            controles["bloco_desligado"] = self.var_controle_off.get().strip() or "air"
            controles["duracao_reset_ms"] = max(100, int(self.var_controle_duracao.get()))
            controles["intervalo_min_jogadas_ms"] = max(0, int(self.var_intervalo_min.get()))
            controles["modo_botao"] = bool(self.var_controle_modo_botao.get())
            controles["terracota_x"] = self.var_terracota_x.get().strip() or "red_terracotta"
            controles["terracota_o"] = self.var_terracota_o.get().strip() or "blue_terracotta"
            controles["terracota_p2"] = self.var_terracota_p2.get().strip() or "yellow_terracotta"
        except Exception:
            pass

        hotspot = copy.deepcopy(self.config.get("hotspot", CONFIG_PADRAO["hotspot"]))
        try:
            hotspot.update({
                "habilitar": bool(self.var_hotspot_habilitar.get()),
                "nome": self.var_hotspot_nome.get().strip() or "PORTA ZERO",
                "senha": self.var_hotspot_senha.get(),
                "ip": self.var_hotspot_ip.get().strip() or "10.0.1.13/24",
                "nome_backup": self.var_hotspot_backup.get().strip() or "PORTA ZERO backup",
                "desligar_sem_internet": bool(self.var_hotspot_desligar.get()),
                "verificar_a_cada_segundos": max(5, int(self.var_hotspot_intervalo.get())),
                "interface": self.var_hotspot_interface.get().strip(),
            })
        except (AttributeError, ValueError):
            pass

        return {
            "host": self.var_host.get().strip(),
            "porta": int(self.var_porta.get().strip()),
            "senha": self.var_senha.get(),
            "usuario_op": self.var_usuario.get().strip(),
            "modo_offline": bool(self.var_offline.get()) or not TEM_RCON,
            "bloco_base": self.var_bloco_base.get().strip(),
            "bloco_x": self.var_bloco_x.get().strip(),
            "bloco_o": self.var_bloco_o.get().strip(),
            "coordenadas": coord,
            "tela": {
                "tela_cheia": bool(self.var_tela_cheia.get()),
                "largura": larg, "altura": alt,
                "escala": float(self.var_escala.get()),
                "tamanho_tabuleiro": max(240, int(self.var_tabuleiro.get())),
                "mostrar_simbolos": bool(self.var_mostrar_simbolos.get()),
                "mostrar_log": bool(self.var_mostrar_log.get()),
                "largura_log": max(200, int(self.var_largura_log.get())),
                "modo_feira": bool(self.var_modo_feira.get()),
                "modo_demo": bool(self.var_modo_demo.get()),
                "inatividade_segundos": max(15, int(self.var_inatividade.get())),
            },
            "tema": self.var_tema.get(),
            "nomes": {"X": self.var_nome_x.get().strip() or "Humano",
                      "O": self.var_nome_o.get().strip() or "IA"},
            "console": self.config["console"],
            "velha": dict(self.config.get("velha", {"modo": "ia", "dificuldade": "dificil"})),
            "conect4": c4,
            "controles_minecraft": controles,
            "hotspot": hotspot,
        }

    def _testar_conexao(self):
        try: cfg = self._coletar()
        except ValueError:
            self._log_config("Valores inválidos.", "erro"); return
        if cfg["modo_offline"]:
            self._log_config("Modo offline ativo.", "aviso"); return
        self._log_config(f"Conectando em {cfg['host']}:{cfg['porta']}...")
        self.root.update_idletasks()
        try:
            with MCRcon(cfg["host"], cfg["senha"], port=cfg["porta"], timeout=5) as m:
                with self._rcon_lock:
                    m.command("say teste")
            self._log_config("Conexão OK.", "ok")
        except Exception as e:
            self._log_config(f"Erro: {e}", "erro")

    def _salvar(self):
        try: cfg = self._coletar()
        except ValueError:
            self._log_config("Valores inválidos.", "erro"); return
        self.config = cfg
        self.hotspot.cfg = cfg.get("hotspot", {})
        salvar_config(cfg)
        self._log_config("Configurações salvas.", "ok")

    def _restaurar_padrao(self):
        self.config = copy.deepcopy(CONFIG_PADRAO)
        salvar_config(self.config)
        self._aplicar_tema()
        self._aplicar_tela()
        self.trocar_tela("config")

    def _iniciar(self, modo):
        try: cfg = self._coletar()
        except ValueError:
            self._log_config("Valores inválidos.", "erro"); return
        self.config = cfg
        salvar_config(cfg)
        self._aplicar_tela()
        self._aplicar_tema()
        self.trocar_tela("jogo", modo)

    # ============================================================
    # TELA DE JOGO (comum)
    # ============================================================
    def _montar_jogo(self, modo):
        self.jogo_atual = modo
        self._entrada_bloqueada = False
        self.frame_atual = tk.Frame(self.root, bg=self.c["fundo"])
        self.frame_atual.pack(fill="both", expand=True)

        topo = tk.Frame(self.frame_atual, bg=self.c["fundo"])
        topo.pack(fill="x", padx=30, pady=(16, 6))

        self._botao(topo, "✕", self.c["painel"], self.c["erro"], self.sair, True).pack(side="right", padx=4)

        self.frame_conteudo = tk.Frame(self.frame_atual, bg=self.c["fundo"])
        self.frame_conteudo.pack(fill="both", expand=True, padx=30, pady=(0, 14))

        if modo == "velha":
            self._montar_velha()
        elif modo == "c4":
            self._montar_c4()
        self._animacao_entrada_jogo(modo)

        self._bind("<c>", lambda e: self.trocar_tela_config())
        self._bind("<Shift-KeyPress-1>", lambda e: self.trocar_tela("jogo", "velha"))
        self._bind("<Shift-KeyPress-2>", lambda e: self.trocar_tela("jogo", "c4"))
        self._bind("<exclam>", lambda e: self.trocar_tela("jogo", "velha"))
        self._bind("<at>", lambda e: self.trocar_tela("jogo", "c4"))

        self.frame_atual.bind("<Motion>", self._atividade, add="+")
        self.frame_atual.bind("<Button>", self._atividade, add="+")
        self.frame_atual.bind("<KeyPress>", self._atividade, add="+")

        self._agendar_retorno()









    def _animacao_entrada_jogo(self, modo):
        """Realça o título com um acento breve e suave ao abrir cada jogo."""
        texto = getattr(self, "lbl_titulo_jogo", None)
        if texto is None or not texto.winfo_exists():
            return
        cor_base = self.c["texto"]
        cor_acento = self.c["destaque"]

        def passo(n=0):
            if not texto.winfo_exists():
                return
            progresso = min(1.0, n / 24.0)
            envelope = math.sin(math.pi * progresso)
            intensidade = 0.68 * envelope
            texto.config(fg=self._misturar_cores(cor_base, cor_acento, intensidade))
            if n < 24:
                aid = self.root.after(20, lambda: passo(n + 1))
                self._anim_ids.append(aid)
            else:
                texto.config(fg=cor_base)

        passo()

    def trocar_tela_config(self):
        self.trocar_tela("config")

    def _reiniciar_atual(self):
        if self.jogo_atual == "velha": self._velha_reiniciar()
        elif self.jogo_atual == "c4":  self._c4_reiniciar()

    def _atividade(self, event=None):
        agora = datetime.datetime.now().timestamp()
        if agora - self._ultima_atividade < 1: return
        self._ultima_atividade = agora
        self._agendar_retorno()

    def _agendar_retorno(self):
        if self._idle_id:
            try: self.root.after_cancel(self._idle_id)
            except Exception: pass
            self._idle_id = None
        t = self.config["tela"]
        if t.get("modo_feira", True) and self.frame_atual:
            self._idle_id = self.root.after(int(t["inatividade_segundos"]) * 1000, self._retorno_feira)

    def _retorno_feira(self):
        if not self.frame_atual: return
        self.placar = {"X":0,"O":0,"Empate":0}
        self.c4_placar = {"P1":0,"P2":0,"Empate":0}
        self.trocar_tela("jogo", "velha")
        self._log_jogo("Modo apresentação: reiniciado por inatividade e máquinas limpas.", "aviso")

    def _log_jogo(self, msg, tag=None):
        self._escrever(getattr(self, "log_jogo", None), msg, tag)

    def _registrar_resultado(self, vencedor, humano):
        self.estatisticas["partidas"] += 1
        if vencedor == "Empate":
            self.estatisticas["empates"] += 1
        elif vencedor == humano:
            self.estatisticas["vitorias"] += 1
        else:
            self.estatisticas["derrotas"] += 1
        duracao = time.monotonic() - self._inicio_partida
        self._log_jogo(
            f"Estatísticas: {self.estatisticas['partidas']} partidas | "
            f"{self.estatisticas['vitorias']}V/{self.estatisticas['derrotas']}D/"
            f"{self.estatisticas['empates']}E | duração {duracao:.1f}s", "aviso")

    # ============================================================
    # JOGO DA VELHA
    # ============================================================
    def _montar_velha(self):
        self.tabuleiro = [None]*9
        self.jogador_atual = "X"
        self.fim_jogo = False
        self.hover = None
        self.linha_venc = None
        self._joycon_ttt_cell = 4
        self._joycon_ttt_ativo = False
        self._joycon_pointer_xy = None

        c = self.c
        t = self.config["tela"]
        velha_cfg = self.config.get("velha", {"modo": "ia", "dificuldade": "dificil"})

        corpo = tk.Frame(self.frame_conteudo, bg=c["fundo"])
        corpo.pack(fill="both", expand=True)
        principal = tk.Frame(corpo, bg=c["fundo"]); principal.pack(side="left", fill="both", expand=True)
        lateral = tk.Frame(corpo, bg=c["fundo"], width=int(t["largura_log"]))
        lateral.pack(side="right", fill="y", padx=(18, 0)); lateral.pack_propagate(False)

        self.lbl_titulo_jogo = tk.Label(principal, text="JOGO DA VELHA", font=self._fonte("titulo"),
                                        bg=c["fundo"], fg=c["texto"])
        self.lbl_titulo_jogo.pack(anchor="center")

        # seletor de modo
        sel = tk.Frame(principal, bg=c["fundo"]); sel.pack(fill="x", pady=(4, 10))
        tk.Label(sel, text="Modo:", font=self._fonte("dica"),
                 bg=c["fundo"], fg=c["subtexto"]).pack(side="left")
        self.var_velha_modo = tk.StringVar(value=velha_cfg.get("modo", "ia"))
        m1 = tk.OptionMenu(sel, self.var_velha_modo, "2p", "ia", command=self._velha_mudar_modo)
        m1.config(font=self._fonte("campo"), bg=c["campo"], fg=c["texto"],
                  relief="flat", highlightthickness=0, width=6)
        m1["menu"].config(bg=c["campo"], fg=c["texto"])
        m1.pack(side="left", padx=(6, 12))

        tk.Label(sel, text="IA:", font=self._fonte("dica"),
                 bg=c["fundo"], fg=c["subtexto"]).pack(side="left")
        self.var_velha_dif = tk.StringVar(value=velha_cfg.get("dificuldade", "dificil"))
        m2 = tk.OptionMenu(sel, self.var_velha_dif, "facil", "medio", "dificil", "impossivel",
                           command=self._velha_mudar_dif)
        m2.config(font=self._fonte("campo"), bg=c["campo"], fg=c["texto"],
                  relief="flat", highlightthickness=0, width=10)
        m2["menu"].config(bg=c["campo"], fg=c["texto"])
        m2.pack(side="left", padx=(6, 0))

        cards = tk.Frame(principal, bg=c["fundo"]); cards.pack(fill="x", pady=(0, 8))
        def card(lbl, cor):
            box = tk.Frame(cards, bg=c["painel"], padx=18, pady=10)
            box.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(box, text=lbl, font=self._fonte("mini"), bg=c["painel"], fg=c["subtexto"]).pack(anchor="w")
            v = tk.Label(box, text="0", font=self._fonte("numero"), bg=c["painel"], fg=cor)
            v.pack(anchor="w"); return v
        self.lbl_px = card(self.config["nomes"]["X"], c["x"])
        self.lbl_pe = card("EMPATES", c["texto"])
        self.lbl_po = card(self.config["nomes"]["O"], c["o"])

        res = tk.Frame(principal, bg=c["fundo"]); res.pack(fill="x", pady=(0, 8))
        self._botao(res, "NOVO JOGO", c["destaque"], c["fundo"], self._novo_jogo_velha, True).pack(side="left", expand=True, fill="x", padx=3)
        self._botao(res, "CALIBRAR 9 CASAS", c["campo"], c["texto"], self._joycon_calibrar_mira, True).pack(side="left", expand=True, fill="x", padx=3)

        self.lbl_status = tk.Label(principal, font=self._fonte("status"), bg=c["fundo"], fg=c["x"])
        self.lbl_status.pack(pady=(2, 5))
        self.lbl_joycon_info = tk.Label(principal, text="", font=self._fonte("mini"),
                                        bg=c["fundo"], fg=c["subtexto"])
        self.lbl_joycon_info.pack(pady=(0, 5))

        mol = tk.Frame(principal, bg=c["painel"], padx=12, pady=12); mol.pack(expand=True)
        lim_a = max(300, int(self.root.winfo_screenheight() * 0.55))
        lim_l = max(300, int(self.root.winfo_screenwidth() * 0.48))
        self.tam = min(int(t["tamanho_tabuleiro"] * float(t.get("escala", 1.0))), lim_a, lim_l, 620)
        self.canvas = tk.Canvas(mol, width=self.tam, height=self.tam, bg=c["painel"], highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._velha_clique)
        self.canvas.bind("<Motion>", self._velha_hover)
        self.canvas.bind("<Leave>", lambda e: self._velha_set_hover(None))

        box = tk.Frame(lateral, bg=c["painel"], padx=14, pady=14); box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text="PARTIDA", font=self._fonte("mini"), bg=c["painel"], fg=c["subtexto"]).pack(anchor="w")
        tk.Label(box, text="Minecraft Arcade", font=self._fonte("secao"),
                 bg=c["painel"], fg=c["texto"]).pack(anchor="w", pady=(8, 0))
        ac = tk.Frame(lateral, bg=c["painel"], padx=10, pady=10); ac.pack(fill="x", pady=(0, 10))
        self._botao(ac, "NOVO JOGO", c["destaque"], c["fundo"], self._novo_jogo_velha).pack(fill="x", pady=3)
        self._botao(ac, "Zerar placar", c["campo"], c["texto"], self._zerar_placar_velha, True).pack(fill="x", pady=3)

        if t["mostrar_log"]:
            lg = tk.Frame(lateral, bg=c["painel"], padx=12, pady=12); lg.pack(fill="both", expand=True)
            tk.Label(lg, text="EVENTOS", font=self._fonte("mini"), bg=c["painel"], fg=c["subtexto"]).pack(anchor="w", pady=(0, 6))
            self.log_jogo = self._log_widget(lg, 14)
            self.log_jogo.pack(fill="both", expand=True)
        else:
            self.log_jogo = None

        mapa = {"7":0,"8":1,"9":2,"4":3,"5":4,"6":5,"1":6,"2":7,"3":8}
        for k, p_ in mapa.items():
            self._bind(k, lambda e, p=p_: self._velha_jogar(p))
        self._bind("<Left>", lambda e: self._joycon_mov_velha(-1, 0))
        self._bind("<Right>", lambda e: self._joycon_mov_velha(1, 0))
        self._bind("<Up>", lambda e: self._joycon_mov_velha(0, -1))
        self._bind("<Down>", lambda e: self._joycon_mov_velha(0, 1))
        self._bind("<Return>", lambda e: self._velha_jogar(self._joycon_ttt_cell))
        self._bind("<space>", lambda e: self._velha_jogar(self._joycon_ttt_cell))

        self._atualizar_placar()
        self._atualizar_status()
        self._velha_desenhar_tudo()
        self._limpar_coordenadas_velha()
        self._atualizar_controle_jogador("velha", "X")
        self._dino_inicio("velha")
        self._tab_update()
        self._log_jogo("Partida pronta. Humano começa.", "ok")

    def _velha_mudar_modo(self, valor):
        if "velha" not in self.config:
            self.config["velha"] = {"modo": valor, "dificuldade": "dificil"}
        else:
            self.config["velha"]["modo"] = valor
        try: salvar_config(self.config)
        except Exception: pass
        self._velha_reiniciar()
        self._log_jogo(f"Modo: {'2 jogadores' if valor == '2p' else 'vs IA'}", "aviso")

    def _velha_mudar_dif(self, valor):
        if "velha" not in self.config:
            self.config["velha"] = {"modo": "ia", "dificuldade": valor}
        else:
            self.config["velha"]["dificuldade"] = valor
        try: salvar_config(self.config)
        except Exception: pass
        self._log_jogo(f"Dificuldade da IA: {valor}", "aviso")

    def _velha_desenhar_tudo(self):
        cv, c = self.canvas, self.c
        cv.delete("all")
        gap = self.tam * 0.012
        for i in range(9):
            x1, y1, x2, y2 = self._velha_celula(i)
            cor = c["casa"]
            if self.linha_venc and i in self.linha_venc: cor = c["campo"]
            self._velha_retangulo(x1+gap, y1+gap, x2-gap, y2-gap,
                                  self.tam*0.03, cor, f"casa{i}", c["linha"])
            cv.create_text(x1+gap*2.2, y1+gap*2, text=str(i), anchor="nw",
                           font=self._fonte("dica"), fill=c["linha"], tags=f"num{i}")
            if self.tabuleiro[i] and self.config["tela"].get("mostrar_simbolos", True):
                self._velha_simbolo(i, self.tabuleiro[i])
            if self._joycon_ttt_ativo and i == self._joycon_ttt_cell:
                cv.itemconfig(f"casa{i}", outline=c["destaque"], width=max(3, int(self.tam*0.012)))
        if self.linha_venc:
            a, b = self.linha_venc[0], self.linha_venc[2]
            ax1, ay1, ax2, ay2 = self._velha_celula(a)
            bx1, by1, bx2, by2 = self._velha_celula(b)
            cv.create_line((ax1+ax2)/2,(ay1+ay2)/2,(bx1+bx2)/2,(by1+by2)/2,
                           width=max(6, self.tam*0.02), fill=c["vitoria"], capstyle="round")
        if self.hover is not None and self.tabuleiro[self.hover] is None and not self.fim_jogo:
            cv.itemconfig(f"casa{self.hover}", fill=c["casa_hover"])
        self._velha_desenhar_ponteiro()

    def _velha_celula(self, i):
        cel = self.tam / 3
        col, lin = i % 3, i // 3
        return col*cel, lin*cel, (col+1)*cel, (lin+1)*cel

    def _velha_retangulo(self, x1, y1, x2, y2, r, cor, tag, borda=None):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
               x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        self.canvas.create_polygon(pts, smooth=True, fill=cor,
                                   outline=borda or "", width=1 if borda else 0, tags=tag)

    def _velha_simbolo(self, i, jog, escala=1.0):
        cv, c = self.canvas, self.c
        x1, y1, x2, y2 = self._velha_celula(i)
        cx, cy = (x1+x2)/2, (y1+y2)/2
        r = (x2-x1) * 0.28 * escala
        w = max(4, self.tam*0.03*escala)
        tag = f"simb{i}"
        cv.delete(tag)
        if jog == "X":
            cv.create_line(cx-r,cy-r,cx+r,cy+r, width=w, fill=c["x"], capstyle="round", tags=tag)
            cv.create_line(cx+r,cy-r,cx-r,cy+r, width=w, fill=c["x"], capstyle="round", tags=tag)
        else:
            cv.create_oval(cx-r,cy-r,cx+r,cy+r, width=w, outline=c["o"], tags=tag)

    def _velha_animar_simbolo(self, i, jog):
        """Faz a peça crescer com um pequeno ressalto ao ser colocada."""
        if not getattr(self, "canvas", None) or not self.canvas.winfo_exists():
            return
        quadros = 10

        def passo(n=0):
            if not getattr(self, "canvas", None) or not self.canvas.winfo_exists():
                return
            progresso = min(1.0, n / quadros)
            escala = 1.0 - 0.72 * ((1.0 - progresso) ** 3) + 0.13 * math.sin(math.pi * progresso)
            self._velha_simbolo(i, jog, escala)
            if n < quadros:
                aid = self.root.after(16, lambda: passo(n + 1))
                self._anim_ids.append(aid)

        passo()

    def _velha_pos(self, e):
        if not (0 <= e.x < self.tam and 0 <= e.y < self.tam): return None
        cel = self.tam / 3
        return int(e.y // cel) * 3 + int(e.x // cel)

    def _velha_hover(self, e):
        self._velha_set_hover(self._velha_pos(e))

    def _velha_set_hover(self, pos):
        if pos == self.hover: return
        ant = self.hover
        self.hover = pos
        if ant is not None and self.tabuleiro[ant] is None:
            try: self.canvas.itemconfig(f"casa{ant}", fill=self.c["casa"])
            except Exception: pass
        if pos is not None and self.tabuleiro[pos] is None and not self.fim_jogo:
            try: self.canvas.itemconfig(f"casa{pos}", fill=self.c["casa_hover"])
            except Exception: pass
            self.canvas.config(cursor="hand2")
        else:
            self.canvas.config(cursor="")

    def _velha_clique(self, e):
        if getattr(self, "_entrada_bloqueada", False): return
        p = self._velha_pos(e)
        if p is not None: self._velha_jogar(p)

    def _velha_jogar(self, pos):
        if (getattr(self, "_entrada_bloqueada", False) or self._joycon_calibracao_ativa
                or self.fim_jogo or self.tabuleiro[pos] is not None or not self.frame_atual): return
        modo = self.config.get("velha", {}).get("modo", "ia")
        if modo == "ia" and self.jogador_atual != "X":
            return
        if not self._pode_jogar_agora():
            return
        jog = str(self.jogador_atual)
        self._aplicar_jogada_velha(pos, jog)
        nome = self.config["nomes"][jog]
        self._log_jogo(f"{nome} jogou na casa {pos}.", jog.lower())
        if self._velha_checar_fim():
            self._trocar_sinal_final("velha", jog)
            return
        self.jogador_atual = "O" if jog == "X" else "X"
        self._atualizar_controle_jogador("velha", self.jogador_atual)
        self._atualizar_status()
        self._tab_update()
        if modo == "ia" and self.jogador_atual == "O":
            token = self._token_partida_velha
            self._inicio_pensamento_velha = time.monotonic()
            self.lbl_status.config(text="IA pensando...", fg=self.c["o"])
            self._dino_evento("velha", "thinking")
            self._velha_ia_jogar(token)

    def _velha_ia_jogar(self, token=None):
        if token is not None and token != self._token_partida_velha: return
        if self.fim_jogo or not self.frame_atual: return
        if self.config.get("velha", {}).get("modo", "ia") != "ia": return
        if self.jogador_atual != "O": return
        vazias = [i for i in range(9) if self.tabuleiro[i] is None]
        if not vazias: return
        dif = self.config.get("velha", {}).get("dificuldade", "dificil")
        if dif == "facil":     chance_rand = 0.60
        elif dif == "medio":   chance_rand = 0.25
        else:                  chance_rand = 0.0
        if random.random() < chance_rand:
            melhor = random.choice(vazias)
        else:
            tab = tuple(self.tabuleiro)
            melhor = None
            melhor_score = -10
            for i in vazias:
                nova = list(tab); nova[i] = "O"
                sc = self._velha_minimax(tuple(nova), False)
                if sc > melhor_score:
                    melhor_score = sc
                    melhor = i
        decorrido = (time.monotonic() - getattr(self, "_inicio_pensamento_velha", time.monotonic())) * 1000
        restante = max(0, int(max(DELAY_MIN_IA_MS, self._intervalo_min_jogadas_ms()) - decorrido))
        self.root.after(restante, lambda p=melhor, t=token: self._velha_aplicar_ia(p, t))

    def _velha_aplicar_ia(self, melhor, token=None):
        if token is not None and token != self._token_partida_velha: return
        if self.fim_jogo or not self.frame_atual or self.jogador_atual != "O": return
        if self._joycon_calibracao_ativa:
            self.root.after(100, lambda: self._velha_aplicar_ia(melhor, token))
            return
        if not self._pode_jogar_agora():
            self.root.after(50, lambda: self._velha_aplicar_ia(melhor, token))
            return
        self._aplicar_jogada_velha(melhor, "O")
        self._log_jogo(f"IA jogou na casa {melhor}.", "o")
        if self._velha_checar_fim():
            self._trocar_sinal_final("velha", "O")
            return
        self.jogador_atual = "X"
        self._atualizar_controle_jogador("velha", self.jogador_atual)
        self._atualizar_status()
        self._tab_update()

    def _aplicar_jogada_velha(self, pos, jogador):
        """Registra uma jogada com jogador explícito; a peça nunca depende do próximo turno."""
        jogador = "X" if jogador == "X" else "O"
        self.tabuleiro[int(pos)] = jogador
        self._tab_last_move = f"Velha_Casa_{int(pos)}_{jogador}"
        self._velha_animar_simbolo(int(pos), jogador)
        self._atualizar_coordenada_casa_velha(int(pos), jogador)
        self._dino_evento("velha", "move")
        self._tab_update()

    def _trocar_sinal_final(self, jogo, jogador_atual):
        """Inverte o sinal exatamente uma vez na jogada que encerra a partida."""
        atributo = "_sinal_final_velha_aplicado" if jogo == "velha" else "_sinal_final_c4_aplicado"
        if getattr(self, atributo, False):
            return
        setattr(self, atributo, True)
        if jogo == "velha":
            proximo = "O" if jogador_atual == "X" else "X"
        else:
            proximo = "P2" if jogador_atual == "P1" else "P1"
        self._atualizar_controle_jogador(jogo, proximo)

    def _velha_minimax(self, tab, ia_vez):
        return self._velha_minimax_cache(tab, ia_vez)

    @lru_cache(maxsize=200000)
    def _velha_minimax_cache(self, tab, ia_vez):
        for a, b, c in LINHAS_VITORIA:
            if tab[a] and tab[a] == tab[b] == tab[c]:
                return 1 if tab[a] == "O" else -1
        if all(tab): return 0
        if ia_vez:
            melhor = -10
            for i in range(9):
                if tab[i] is None:
                    nova = list(tab); nova[i] = "O"
                    melhor = max(melhor, self._velha_minimax_cache(tuple(nova), False))
            return melhor
        else:
            melhor = 10
            for i in range(9):
                if tab[i] is None:
                    nova = list(tab); nova[i] = "X"
                    melhor = min(melhor, self._velha_minimax_cache(tuple(nova), True))
            return melhor

    def _velha_checar_fim(self):
        linha = None
        for a, b, c in LINHAS_VITORIA:
            if self.tabuleiro[a] and self.tabuleiro[a] == self.tabuleiro[b] == self.tabuleiro[c]:
                linha = (a, b, c); break
        if linha:
            self.fim_jogo = True
            self.linha_venc = linha
            venc = self.tabuleiro[linha[0]]
            self._dino_evento("velha", "x_win" if venc == "X" else "o_win")
            self._dino_evento("velha", "o_lose" if venc == "X" else "x_lose")
            self._tab_last_game = "Jogo_da_Velha"
            self._tab_last_winner = venc
            self.placar[venc] += 1
            self._registrar_resultado(venc, "X")
            self._atualizar_placar()
            nome = self.config["nomes"][venc]
            self.lbl_status.config(text=f"{nome} venceu!", fg=self.c["vitoria"])
            self._rcon(f'say {nome} venceu o Jogo da Velha!')
            self._log_jogo(f"Fim: {nome} venceu.", "ok")
            self._tab_update()
            self._velha_desenhar_tudo()
            return True
        if all(self.tabuleiro):
            self.fim_jogo = True
            self._dino_evento("velha", "draw")
            self.placar["Empate"] += 1
            self._registrar_resultado("Empate", "X")
            self._atualizar_placar()
            self.lbl_status.config(text="Empate!", fg=self.c["subtexto"])
            self._rcon_async("say Empate no Jogo da Velha!")
            self._tab_last_game = "Jogo_da_Velha"
            self._tab_last_winner = "Empate"
            self._tab_update()
            self._log_jogo("Fim: Empate.", "aviso")
            return True
        return False

    def _velha_reiniciar(self):
        self._token_partida_velha += 1
        self._inicio_partida = time.monotonic()
        self._sinal_final_velha_aplicado = False
        self.tabuleiro = [None]*9
        self.jogador_atual = "X"
        self.fim_jogo = False
        self.linha_venc = None
        self._velha_desenhar_tudo()
        self._atualizar_status()
        self._atualizar_controle_jogador("velha", "X")
        self._tab_update()
        self._rcon_async("say Nova partida de Jogo da Velha!")
        self._log_jogo("Reiniciado.", "ok")

    def _atualizar_coordenada_casa_velha(self, pos, jogador):
        """Atualiza a casa: modo botão usa terracota sobre redstone; modo normal usa o bloco base."""
        try:
            coord = self.config["coordenadas"][str(pos)]
            cfg = self.config["controles_minecraft"]
            if self._modo_botao_ativo():
                terracota = cfg.get("terracota_x", "red_terracotta") if jogador == "X" else cfg.get("terracota_o", "blue_terracotta")
                self._pulso_modo_botao(coord, terracota, f"velha-{pos}")
                return
            bloco = cfg.get("bloco_ligado", "redstone_block") if jogador == "X" else cfg.get("bloco_desligado", "air")
            self._rcon_setblock(*coord, bloco, silencioso=True, forcar=True, assincrono=True)
        except Exception as e:
            self._log_jogo(f"Coordenada da casa {pos} falhou: {e}", "erro")

    def _limpar_coordenadas_velha(self):
        """Remove as saídas das nove casas sem acionar a coordenada de reset."""
        try:
            off = self.config["controles_minecraft"].get("bloco_desligado", "air")
            for coord in self.config.get("coordenadas", {}).values():
                self._rcon_setblock(*coord, off, silencioso=True, forcar=True)
                if self._modo_botao_ativo():
                    self._rcon_setblock(int(coord[0]), int(coord[1]) + 1, int(coord[2]), off, silencioso=True, forcar=True)
        except Exception as e:
            self._log_jogo(f"Limpeza das coordenadas da Velha falhou: {e}", "erro")

    def _atualizar_placar(self):
        if not getattr(self, "lbl_px", None): return
        self.lbl_px.config(text=str(self.placar["X"]))
        self.lbl_pe.config(text=str(self.placar["Empate"]))
        self.lbl_po.config(text=str(self.placar["O"]))

    def _atualizar_status(self):
        if not getattr(self, "lbl_status", None): return
        if self.fim_jogo: return
        modo = self.config.get("velha", {}).get("modo", "ia")
        nome = self.config["nomes"][self.jogador_atual]
        if modo == "ia" and self.jogador_atual == "O":
            nome = f"{nome} (pensando...)"
        cor = self.c["x"] if self.jogador_atual == "X" else self.c["o"]
        self.lbl_status.config(text=f"Vez de {nome}", fg=cor)

    def _zerar_placar_velha(self):
        self.placar = {"X":0,"O":0,"Empate":0}
        self._atualizar_placar()

    # ============================================================
    # CONECT 4
    # ============================================================
    def _montar_c4(self):
        c4 = self.config["conect4"]
        self.c4_cols = int(c4["colunas"])
        self.c4_lins = int(c4["linhas"])
        self.c4_dificuldade = c4.get("dificuldade", "medio")
        self.c4_modo = c4.get("modo", "ia") if c4.get("modo", "ia") in ("ia", "2p") else "ia"
        self.c4_grade = [[None]*self.c4_cols for _ in range(self.c4_lins)]
        self.c4_jogador = "P1"
        self.c4_jogadas = 0
        self.c4_fim = False
        self.c4_venc = None
        self.c4_pensando = False
        self._c4_animando = None
        self._c4_hover_col = self.c4_cols // 2

        c = self.c
        t = self.config["tela"]
        corpo = tk.Frame(self.frame_conteudo, bg=c["fundo"])
        corpo.pack(fill="both", expand=True)
        principal = tk.Frame(corpo, bg=c["fundo"]); principal.pack(side="left", fill="both", expand=True)
        lateral = tk.Frame(corpo, bg=c["fundo"], width=int(t["largura_log"]))
        lateral.pack(side="right", fill="y", padx=(18, 0)); lateral.pack_propagate(False)

        self.lbl_titulo_jogo = tk.Label(principal, text="CONECT 4", font=self._fonte("titulo"),
                                        bg=c["fundo"], fg=c["texto"])
        self.lbl_titulo_jogo.pack(anchor="center")

        modo_row = tk.Frame(principal, bg=c["fundo"]); modo_row.pack(fill="x", pady=(0, 6))
        tk.Label(modo_row, text="Modo:", font=self._fonte("dica"),
                 bg=c["fundo"], fg=c["subtexto"]).pack(side="left")
        modo_texto = "vs IA" if self.c4_modo == "ia" else "2 jogadores"
        self.var_c4_modo_jogo = tk.StringVar(value=modo_texto)
        menu_modo = tk.OptionMenu(modo_row, self.var_c4_modo_jogo, "vs IA", "2 jogadores",
                                  command=self._c4_mudar_modo)
        menu_modo.config(font=self._fonte("campo"), bg=c["campo"], fg=c["texto"],
                         relief="flat", highlightthickness=0, width=16)
        menu_modo["menu"].config(bg=c["campo"], fg=c["texto"])
        menu_modo.pack(side="left", padx=(8, 0))
        self.lbl_c4_modo = tk.Label(modo_row, text=modo_texto, font=self._fonte("dica"),
                                    bg=c["fundo"], fg=c["destaque"])
        self.lbl_c4_modo.pack(side="left", padx=(10, 0))

        subtitulo = "Jogador 1 ●  vs  IA ●" if self.c4_modo == "ia" else "Jogador 1 ●  vs  Jogador 2 ●"
        self.lbl_c4_subtitulo = tk.Label(principal, text=subtitulo, font=self._fonte("dica"),
                                         bg=c["fundo"], fg=c["subtexto"])
        self.lbl_c4_subtitulo.pack(anchor="w", pady=(0, 8))

        dif = tk.Frame(principal, bg=c["fundo"]); dif.pack(fill="x", pady=(0, 6))
        tk.Label(dif, text="Dificuldade:", font=self._fonte("dica"),
                 bg=c["fundo"], fg=c["subtexto"]).pack(side="left")
        self.var_c4_dif_jogo = tk.StringVar(value=self.c4_dificuldade)
        m = tk.OptionMenu(dif, self.var_c4_dif_jogo, "facil", "medio", "dificil", "impossivel",
                          command=self._c4_mudar_dificuldade)
        m.config(font=self._fonte("campo"), bg=c["campo"], fg=c["texto"],
                 relief="flat", highlightthickness=0, width=12)
        m["menu"].config(bg=c["campo"], fg=c["texto"])
        m.pack(side="left", padx=(8, 0))

        cards = tk.Frame(principal, bg=c["fundo"]); cards.pack(fill="x", pady=(6, 8))
        def card(lbl, cor):
            box = tk.Frame(cards, bg=c["painel"], padx=18, pady=10)
            box.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(box, text=lbl, font=self._fonte("mini"), bg=c["painel"], fg=c["subtexto"]).pack(anchor="w")
            v = tk.Label(box, text="0", font=self._fonte("numero"), bg=c["painel"], fg=cor)
            v.pack(anchor="w"); return v
        self.lbl_c4_p1 = card("Humano", c["x"])
        self.lbl_c4_pe = card("EMPATES", c["texto"])
        self.lbl_c4_p2 = card("IA", c["o"])
        self._atualizar_placar_c4()

        res = tk.Frame(principal, bg=c["fundo"]); res.pack(fill="x", pady=(0, 8))
        self._botao(res, "NOVO JOGO", c["destaque"], c["fundo"], self._novo_jogo_c4, True).pack(side="left", expand=True, fill="x", padx=3)

        self.lbl_status_c4 = tk.Label(principal, font=self._fonte("status"),
                                      bg=c["fundo"], fg=c["x"])
        self.lbl_status_c4.pack(pady=(2, 5))
        self.lbl_joycon_info = tk.Label(principal, text="", font=self._fonte("mini"),
                                        bg=c["fundo"], fg=c["subtexto"])
        self.lbl_joycon_info.pack(pady=(0, 5))

        mol = tk.Frame(principal, bg=c["fundo"], padx=16, pady=14)
        mol.pack(fill="both", expand=True)
        self.root.update_idletasks()
        escala = float(t.get("escala", 1.0))
        base = max(28, int(t.get("tamanho_tabuleiro", 560) / 7))
        area_w = max(280, principal.winfo_width() - 36)
        area_h = max(260, principal.winfo_height() - 270)
        cel = int(min(base * escala, area_w / self.c4_cols,
                      area_h / (self.c4_lins + 0.78), 110))
        cel = max(24, cel)
        self.c4_cel = cel
        w = cel * self.c4_cols
        h = cel * self.c4_lins
        self.canvas_c4_previa = tk.Canvas(mol, width=w, height=max(20, int(cel*0.72)),
                                          bg=c["fundo"], highlightthickness=0)
        self.canvas_c4_previa.pack(anchor="center", pady=(0, 1))
        self.canvas_c4 = tk.Canvas(mol, width=w, height=h, bg=c["fundo"], highlightthickness=0)
        self.canvas_c4.pack(anchor="center", pady=4)
        self.canvas_c4.bind("<Button-1>", self._c4_clique)
        self.canvas_c4.bind("<Motion>", self._c4_hover)
        self.canvas_c4.bind("<Leave>", self._c4_hover_sair)
        self._bind("<Left>", lambda e: self._joycon_mov_c4(-1))
        self._bind("<Right>", lambda e: self._joycon_mov_c4(1))
        self._bind("<Return>", lambda e: self._c4_jogar_coluna(self._c4_hover_col))
        self._bind("<space>", lambda e: self._c4_jogar_coluna(self._c4_hover_col))

        box = tk.Frame(lateral, bg=c["painel"], padx=14, pady=14); box.pack(fill="x", pady=(0, 10))
        tk.Label(box, text="PARTIDA", font=self._fonte("mini"), bg=c["painel"], fg=c["subtexto"]).pack(anchor="w")
        tk.Label(box, text=("Conect 4\nJogador vs IA" if self.c4_modo == "ia" else "Conect 4\n2 jogadores"), justify="left",
                 font=self._fonte("secao"), bg=c["painel"], fg=c["texto"]).pack(anchor="w", pady=(8, 0))
        ac = tk.Frame(lateral, bg=c["painel"], padx=10, pady=10); ac.pack(fill="x", pady=(0, 10))
        self._botao(ac, "NOVO JOGO", c["destaque"], c["fundo"], self._novo_jogo_c4).pack(fill="x", pady=3)
        self._botao(ac, "Zerar placar", c["campo"], c["texto"], self._zerar_placar_c4, True).pack(fill="x", pady=3)

        if t["mostrar_log"]:
            lg = tk.Frame(lateral, bg=c["painel"], padx=12, pady=12); lg.pack(fill="both", expand=True)
            tk.Label(lg, text="EVENTOS", font=self._fonte("mini"), bg=c["painel"], fg=c["subtexto"]).pack(anchor="w", pady=(0, 6))
            self.log_jogo = self._log_widget(lg, 14)
            self.log_jogo.pack(fill="both", expand=True)
        else:
            self.log_jogo = None

        self._c4_desenhar()
        self._atualizar_controle_jogador("conect4", "P1")
        self._dino_inicio("c4")
        self.lbl_status_c4.config(
            text=("Sua vez: analógico + SR ou clique numa coluna." if self.c4_modo == "ia" else "Jogador 1: analógico + SR ou clique numa coluna."),
            fg=c["x"]
        )
        self._limpar_coordenadas_c4()
        self._ultima_jogada_monotonic = 0.0
        self._tab_update()
        self._log_jogo("Conect 4 pronto. " + ("Jogador vs IA." if self.c4_modo == "ia" else "2 jogadores."), "ok")

    def _c4_mudar_modo(self, valor):
        self.c4_modo = "ia" if valor == "vs IA" else "2p"
        self.config["conect4"]["modo"] = self.c4_modo
        try:
            salvar_config(self.config)
        except Exception:
            pass
        texto = "vs IA" if self.c4_modo == "ia" else "2 jogadores"
        if getattr(self, "lbl_c4_modo", None):
            self.lbl_c4_modo.config(text=texto)
        if getattr(self, "lbl_c4_subtitulo", None):
            self.lbl_c4_subtitulo.config(text=("Jogador 1 ●  vs  IA ●" if self.c4_modo == "ia" else "Jogador 1 ●  vs  Jogador 2 ●"))
        self._c4_reiniciar()
        self._log_jogo("Conect 4: " + texto, "aviso")

    def _c4_mudar_dificuldade(self, valor):
        self.c4_dificuldade = valor
        self.config["conect4"]["dificuldade"] = valor
        try: salvar_config(self.config)
        except Exception: pass
        self._log_jogo(f"Dificuldade: {valor}", "aviso")

    @staticmethod
    def _c4_pontos_arredondados(x1, y1, x2, y2, raio):
        raio = max(0.0, min(float(raio), (x2 - x1) / 2, (y2 - y1) / 2))
        return [x1+raio,y1, x2-raio,y1, x2,y1, x2,y1+raio,
                x2,y2-raio, x2,y2, x2-raio,y2, x1+raio,y2,
                x1,y2, x1,y2-raio, x1,y1+raio, x1,y1]

    def _c4_caixa(self, canvas, x1, y1, x2, y2, raio, fill, outline="", width=1):
        pontos = self._c4_pontos_arredondados(x1, y1, x2, y2, raio)
        return canvas.create_polygon(*pontos, smooth=True, fill=fill,
                                     outline=outline, width=width)

    def _c4_animar_queda(self, col, lin, jog):
        if not getattr(self, "canvas_c4", None) or self._c4_animando is not None:
            return
        self._c4_animando = True
        self._c4_animacao_info = (col, lin, jog)
        cel = self.c4_cel
        cx = col * cel + cel / 2
        cor = self.c["x"] if jog == "P1" else self.c["o"]
        raio_inicial = cel * 0.31
        item = self._c4_caixa(self.canvas_c4, cx-raio_inicial, -raio_inicial-cel*0.42,
                              cx+raio_inicial, -cel*0.42+raio_inicial,
                              cel*0.07, fill=cor, outline=self.c.get("x_borda" if jog == "P1" else "o_borda", cor), width=2)
        y_inicio = -cel * 0.42
        y_final = lin * cel + cel / 2
        quadros_queda = 18
        quadros_impacto = 7

        def passo(n=0):
            if not self.canvas_c4.winfo_exists():
                self._c4_animando = None
                self._c4_animacao_info = None
                return
            if n <= quadros_queda:
                t = n / quadros_queda
                # Acelera na descida e chega à casa sem prolongar a jogada.
                curva = t * t
                y = y_inicio + (y_final - y_inicio) * curva
                escala_x = 1.0 - 0.04 * t
                escala_y = 1.0 + 0.08 * t
            else:
                t = min(1.0, (n - quadros_queda) / quadros_impacto)
                y = y_final
                # Achata ao tocar a placa e recupera a forma com um pequeno ressalto.
                if t < 0.42:
                    pressao = math.sin((t / 0.42) * math.pi / 2)
                    escala_x = 1.0 + 0.24 * pressao
                    escala_y = 1.0 - 0.32 * pressao
                else:
                    retorno = (t - 0.42) / 0.58
                    ondulacao = math.sin(math.pi * retorno)
                    escala_x = 1.0 + 0.24 * (1.0 - retorno) - 0.05 * ondulacao
                    escala_y = 1.0 - 0.32 * (1.0 - retorno) + 0.07 * ondulacao
            rx = cel * 0.31 * escala_x
            ry = cel * 0.31 * escala_y
            pontos = self._c4_pontos_arredondados(cx-rx, y-ry, cx+rx, y+ry,
                                                  min(rx, ry) * 0.22)
            self.canvas_c4.coords(item, *pontos)
            if n < quadros_queda + quadros_impacto:
                self.root.after(12, lambda: passo(n + 1))
            else:
                self.canvas_c4.delete(item)
                self._c4_animando = None
                self._c4_animacao_info = None
                self._c4_desenhar()
        passo()

    def _c4_desenhar(self):
        cv, c = self.canvas_c4, self.c
        # O desenho usa um snapshot estável, inclusive durante a busca da IA.
        if self._c4_simulando and self._c4_grade_visual is not None:
            grade = self._c4_grade_visual
        else:
            grade = [linha[:] for linha in self.c4_grade]
        venc = list(self.c4_venc) if self.c4_venc else []
        cv.delete("all")
        cel = self.c4_cel
        largura = cel * self.c4_cols
        altura = cel * self.c4_lins
        tabuleiro = c.get("tabuleiro", "#27465b")
        sombra = c.get("sombra", "#09121a")
        cores = {"P1": c["x"], "P2": c["o"]}
        bordas_peca = {"P1": c.get("x_borda", c["x"]), "P2": c.get("o_borda", c["o"])}

        # Fundo único e grade de casas quadradas com cantos suaves, no estilo do Jogo da Velha.
        self._c4_caixa(cv, 2, 2, largura-2, altura-2, cel*0.15,
                       fill=tabuleiro, outline=c.get("linha", tabuleiro), width=2)
        alvo = None
        if (self._c4_hover_col is not None and not self.c4_fim and not self.c4_pensando
                and self._c4_animando is None
                and (self.c4_modo != "ia" or self.c4_jogador == "P1")):
            lin_alvo = self._c4_linha_livre(self._c4_hover_col)
            if lin_alvo is not None:
                alvo = (lin_alvo, self._c4_hover_col)

        vencedoras = set(venc)
        margem = cel * 0.065
        for lin in range(self.c4_lins):
            for col in range(self.c4_cols):
                x1 = col * cel + margem
                y1 = lin * cel + margem
                x2 = (col + 1) * cel - margem
                y2 = (lin + 1) * cel - margem
                v = grade[lin][col]
                # Mantém a casa de chegada vazia até a peça animada aterrissar.
                if self._c4_animacao_info and (col, lin) == self._c4_animacao_info[:2]:
                    v = None
                eh_alvo = alvo == (lin, col)
                eh_vencedora = (lin, col) in vencedoras
                fundo = c["casa_hover"] if eh_alvo else c["casa"]
                contorno = c["vitoria"] if eh_vencedora else (c["destaque"] if eh_alvo else c["linha"])
                largura_contorno = 3 if eh_vencedora or eh_alvo else 1
                raio = cel * 0.09
                self._c4_caixa(cv, x1, y1, x2, y2, raio,
                               fill=fundo, outline=contorno, width=largura_contorno)
                if v and self.config["tela"].get("mostrar_simbolos", True):
                    # Peça quadrada menor que a casa, com sombra e borda em tom claro.
                    lado = cel * 0.29
                    px1, py1 = cel*col + cel/2 - lado, cel*lin + cel/2 - lado
                    px2, py2 = cel*col + cel/2 + lado, cel*lin + cel/2 + lado
                    desloc = max(1, cel*0.035)
                    self._c4_caixa(cv, px1, py1+desloc, px2, py2+desloc,
                                   cel*0.07, fill=sombra, outline="", width=0)
                    self._c4_caixa(cv, px1, py1, px2, py2, cel*0.07,
                                   fill=cores[v], outline=bordas_peca[v],
                                   width=max(1, int(cel*0.025)))
        self._c4_desenhar_previa()

    def _c4_desenhar_previa(self):
        cv = getattr(self, "canvas_c4_previa", None)
        if not cv or not cv.winfo_exists():
            return
        cv.delete("all")
        col = self._c4_hover_col
        if col is None or not (0 <= col < self.c4_cols):
            return
        cel = self.c4_cel
        cy = max(10, int(float(cv["height"]) / 2))
        cx = col * cel + cel / 2
        jogador = self.c4_jogador if not self.c4_fim else "P1"
        cor = self.c["x"] if jogador == "P1" else self.c["o"]
        lado = cel * 0.23
        self._c4_caixa(cv, cx-lado, cy-lado, cx+lado, cy+lado, cel*0.06,
                       fill=cor, outline=self.c.get("x_borda" if jogador == "P1" else "o_borda", cor), width=2)

    def _c4_hover(self, e):
        if self._c4_animando is not None:
            return
        col = int(e.x // self.c4_cel)
        if not (0 <= col < self.c4_cols) or self.c4_fim or self.c4_pensando:
            col = None
        elif self.c4_modo == "ia" and self.c4_jogador != "P1":
            col = None
        elif col is not None and not self._c4_coluna_livre(col):
            col = None
        if col != self._c4_hover_col:
            self._c4_hover_col = col
            self._c4_desenhar()
        self.canvas_c4.config(cursor="hand2" if col is not None else "")

    def _c4_hover_sair(self, e=None):
        if self._c4_hover_col is not None:
            self._c4_hover_col = None
            if self._c4_animando is None:
                self._c4_desenhar()
        if getattr(self, "canvas_c4", None) and self.canvas_c4.winfo_exists():
            self.canvas_c4.config(cursor="")

    def _c4_clique(self, e):
        if getattr(self, "_entrada_bloqueada", False): return
        col = int(e.x // self.c4_cel)
        if not (0 <= col < self.c4_cols): return
        self._c4_jogar_coluna(col)

    def _c4_jogar_coluna(self, col):
        if col is None or not (0 <= int(col) < self.c4_cols): return
        col = int(col)
        if col != self._c4_hover_col:
            self._c4_hover_col = col
            self._c4_desenhar()
        if getattr(self, "_entrada_bloqueada", False): return
        if self.c4_fim: return
        if self.c4_pensando:
            self.lbl_status_c4.config(text="Aguarde: a IA está pensando...", fg=self.c["aviso"])
            return
        if self._c4_animando is not None:
            self.lbl_status_c4.config(text="Aguarde: a peça está caindo...", fg=self.c["aviso"])
            return
        if not self._c4_coluna_livre(col): return
        if not self._pode_jogar_agora():
            self.lbl_status_c4.config(text="Aguarde um instante entre as jogadas.", fg=self.c["aviso"])
            return

        if self.c4_modo == "ia":
            if self.c4_jogador != "P1": return
            if self._c4_soltar(col, "P1") is None: return
            if self._c4_verificar_fim():
                self._trocar_sinal_final("conect4", "P1")
                return
            self.c4_jogador = "P2"
            self._atualizar_controle_jogador("conect4", self.c4_jogador)
            self._tab_update()
            self.c4_pensando = True
            self.lbl_status_c4.config(text="IA pensando...", fg=self.c["o"])
            self._rcon_async('title @a actionbar {"text":"IA pensando...","color":"yellow"}')
            self._dino_evento("c4", "thinking")
            token = self._token_partida_c4
            thread = threading.Thread(target=self._c4_ia_jogar, args=(token,), daemon=True)
            thread.start()
            return

        jog = self.c4_jogador
        if self._c4_soltar(col, jog) is None: return
        if self._c4_verificar_fim():
            self._trocar_sinal_final("conect4", jog)
            return
        self.c4_jogador = "P2" if jog == "P1" else "P1"
        self._atualizar_controle_jogador("conect4", self.c4_jogador)
        self._tab_update()
        nome = "Jogador 1" if self.c4_jogador == "P1" else "Jogador 2"
        self.lbl_status_c4.config(text=f"Vez do {nome}: analógico + SR ou clique numa coluna.",
                                  fg=self.c["x"] if self.c4_jogador == "P1" else self.c["o"])

    def _c4_coluna_livre(self, col):
        return self.c4_grade[0][col] is None

    def _c4_linha_livre(self, col):
        for lin in range(self.c4_lins - 1, -1, -1):
            if self.c4_grade[lin][col] is None:
                return lin
        return None

    def _c4_soltar(self, col, jog):
        lin = self._c4_linha_livre(col)
        if lin is None: return None
        # Registro atômico: a primeira jogada também atualiza o relógio.
        self.c4_grade[lin][col] = jog
        self.c4_jogadas = getattr(self, "c4_jogadas", 0) + 1
        self._ultima_jogada_monotonic = time.monotonic()
        self._tab_last_move = f"Conect_4_Jogada_{self.c4_jogadas}_Coluna_{col + 1}_{jog}"
        self._dino_evento("c4", "move")
        self._c4_animar_queda(col, lin, jog)
        try:
            coord = self.config["conect4"]["coordenadas_colunas"][str(col)]
            cfg = self.config["controles_minecraft"]
            if self._modo_botao_ativo():
                terracota = cfg.get("terracota_x", "red_terracotta") if jog == "P1" else cfg.get("terracota_p2", "yellow_terracotta")
                self._pulso_modo_botao(coord, terracota, f"c4-{col}")
            else:
                bloco = cfg.get("bloco_ligado", "redstone_block") if jog == "P1" else cfg.get("bloco_desligado", "air")
                self._rcon_setblock(*coord, bloco, silencioso=True, forcar=True, assincrono=True)
        except Exception as e:
            self._log_jogo(f"Coordenada da coluna {col + 1} falhou: {e}", "erro")
        self._tab_update()
        self._log_jogo(f"Jogada {self.c4_jogadas}: {'X/P1' if jog=='P1' else 'O/P2'} -> coluna {col+1}, linha {lin+1}", jog)
        return lin

    def _limpar_coordenadas_c4(self):
        try:
            off = self.config["controles_minecraft"].get("bloco_desligado", "air")
            for coord in self.config["conect4"].get("coordenadas_colunas", {}).values():
                self._rcon_setblock(*coord, off, silencioso=True, forcar=True)
                if self._modo_botao_ativo():
                    self._rcon_setblock(int(coord[0]), int(coord[1]) + 1, int(coord[2]), off, silencioso=True, forcar=True)
        except Exception as e:
            self._log_jogo(f"Limpeza das coordenadas do Conect 4 falhou: {e}", "erro")

    def _c4_ia_jogar(self):
        if self.c4_modo != "ia" or self.jogo_atual != "c4" or self.c4_fim: return
        token = self._token_partida_c4
        self._c4_grade_visual = [linha[:] for linha in self.c4_grade]
        self._c4_simulando = True
        cfg = DIFICULDADES.get(self.c4_dificuldade, DIFICULDADES["medio"])
        livres = [c for c in range(self.c4_cols) if self._c4_coluna_livre(c)]
        if not livres:
            self.c4_pensando = False
            self._c4_simulando = False
            self._c4_grade_visual = None
            return
        self._rcon_async('title @a actionbar {"text":"IA pensando...","color":"yellow"}')
        inicio_pensamento = time.monotonic()
        def calcular():
            # O minimax usa a grade real como memória de trabalho. Durante
            # essa simulação, nenhuma rotina de desenho pode ler a grade.
            with self._c4_sim_lock:
                col = None
                if random.random() < cfg["chance_aleatoria"]:
                    col = random.choice(livres)
                else:
                    col = self._c4_melhor_coluna(cfg["profundidade"])
                if col is None:
                    col = random.choice(livres)

            # Mesmo que o cálculo termine rápido, mantenha o estado
            # "IA pensando..." por pelo menos DELAY_MIN_IA_MS.
            decorrido_ms = (time.monotonic() - inicio_pensamento) * 1000.0
            restante_ms = max(0, int(max(DELAY_MIN_IA_MS, self._intervalo_min_jogadas_ms()) - decorrido_ms))
            self.root.after(restante_ms, lambda t=token, escolha=col: self._c4_terminar_calculo_ia(escolha, t))
        threading.Thread(target=calcular, daemon=True).start()

    def _c4_terminar_calculo_ia(self, col, token=None):
        self._c4_simulando = False
        self._c4_grade_visual = None
        self._c4_aplicar_ia(col, token)

    def _c4_aplicar_ia(self, col, token=None):
        if token is not None and token != self._token_partida_c4: return
        if self.c4_modo != "ia": return
        if self.c4_fim or not self.frame_atual: return
        if self.jogo_atual != "c4": return
        if not self._pode_jogar_agora():
            restante = max(40, int((self._intervalo_min_jogadas_ms() / 1000 -
                                    (time.monotonic() - self._ultima_jogada_monotonic)) * 1000))
            self.root.after(restante, lambda: self._c4_aplicar_ia(col, token))
            return
        jog = "P2"
        if self._c4_soltar(col, jog) is None:
            self.c4_pensando = False
            return
        self.c4_pensando = False
        if self._c4_verificar_fim():
            self._trocar_sinal_final("conect4", "P2")
            return
        self.c4_jogador = "P1"
        self._atualizar_controle_jogador("conect4", self.c4_jogador)
        self._tab_update()
        self.lbl_status_c4.config(text="Sua vez.", fg=self.c["x"])
        self._rcon_async('title @a actionbar {"text":"Sua vez","color":"red"}')

    def _c4_melhor_coluna(self, prof):
        melhor_col = None
        melhor_sc = -10**9
        centro = self.c4_cols // 2
        livres = [c for c in range(self.c4_cols) if self._c4_coluna_livre(c)]
        livres.sort(key=lambda c: abs(c - centro))
        alpha, beta = -10**9, 10**9
        for col in livres:
            lin = self._c4_linha_livre(col)
            if lin is None: continue
            self.c4_grade[lin][col] = "P2"
            sc = self._c4_minimax(prof-1, False, alpha, beta)
            self.c4_grade[lin][col] = None
            if sc > melhor_sc:
                melhor_sc = sc; melhor_col = col
            alpha = max(alpha, sc)
        return melhor_col

    def _c4_minimax(self, prof, maximizando, alpha, beta):
        v = self._c4_avaliar()
        if v in (100000, -100000):
            return v + (10 * prof if v > 0 else -10 * prof)
        if prof == 0:
            return v
        livres = [c for c in range(self.c4_cols) if self._c4_coluna_livre(c)]
        if not livres:
            return 0
        if maximizando:
            val = -10**9
            for col in livres:
                lin = self._c4_linha_livre(col)
                self.c4_grade[lin][col] = "P2"
                val = max(val, self._c4_minimax(prof-1, False, alpha, beta))
                self.c4_grade[lin][col] = None
                alpha = max(alpha, val)
                if alpha >= beta: break
            return val
        else:
            val = 10**9
            for col in livres:
                lin = self._c4_linha_livre(col)
                self.c4_grade[lin][col] = "P1"
                val = min(val, self._c4_minimax(prof-1, True, alpha, beta))
                self.c4_grade[lin][col] = None
                beta = min(beta, val)
                if alpha >= beta: break
            return val

    def _c4_avaliar(self):
        v = self._c4_quem_venceu()
        if v == "P2": return 100000
        if v == "P1": return -100000
        if all(self.c4_grade[0][c] is not None for c in range(self.c4_cols)):
            return 0
        g = self.c4_grade
        L, C = self.c4_lins, self.c4_cols
        score = 0
        pesos = {1: 1, 2: 10, 3: 100}
        def avaliar(cells):
            nao_vazio = [g[a][b] for a, b in cells if g[a][b] is not None]
            if not nao_vazio: return 0
            p1 = nao_vazio.count("P1"); p2 = nao_vazio.count("P2")
            if p1 and p2: return 0
            if p2: return pesos.get(p2, 0)
            if p1: return -pesos.get(p1, 0)
            return 0
        for lin in range(L):
            for col in range(C - 3):
                score += avaliar([(lin,col),(lin,col+1),(lin,col+2),(lin,col+3)])
        for lin in range(L - 3):
            for col in range(C):
                score += avaliar([(lin,col),(lin+1,col),(lin+2,col),(lin+3,col)])
        for lin in range(L - 3):
            for col in range(C - 3):
                score += avaliar([(lin,col),(lin+1,col+1),(lin+2,col+2),(lin+3,col+3)])
        for lin in range(3, L):
            for col in range(C - 3):
                score += avaliar([(lin,col),(lin-1,col+1),(lin-2,col+2),(lin-3,col+3)])
        centro = C // 2
        for lin in range(L):
            if g[lin][centro] == "P2": score += 3
            elif g[lin][centro] == "P1": score -= 3
        return score

    def _c4_quem_venceu(self):
        g = self.c4_grade
        L, C = self.c4_lins, self.c4_cols
        for lin in range(L):
            for col in range(C - 3):
                v = g[lin][col]
                if v and v == g[lin][col+1] == g[lin][col+2] == g[lin][col+3]:
                    return v
        for lin in range(L - 3):
            for col in range(C):
                v = g[lin][col]
                if v and v == g[lin+1][col] == g[lin+2][col] == g[lin+3][col]:
                    return v
        for lin in range(L - 3):
            for col in range(C - 3):
                v = g[lin][col]
                if v and v == g[lin+1][col+1] == g[lin+2][col+2] == g[lin+3][col+3]:
                    return v
        for lin in range(3, L):
            for col in range(C - 3):
                v = g[lin][col]
                if v and v == g[lin-1][col+1] == g[lin-2][col+2] == g[lin-3][col+3]:
                    return v
        return None

    def _c4_linha_vencedora(self):
        g = self.c4_grade
        L, C = self.c4_lins, self.c4_cols
        def ok(cells):
            v = g[cells[0][0]][cells[0][1]]
            return v if v and all(g[a][b] == v for a,b in cells) else None
        for lin in range(L):
            for col in range(C - 3):
                v = ok([(lin,col),(lin,col+1),(lin,col+2),(lin,col+3)])
                if v: return v, [(lin,col),(lin,col+1),(lin,col+2),(lin,col+3)]
        for lin in range(L - 3):
            for col in range(C):
                v = ok([(lin,col),(lin+1,col),(lin+2,col),(lin+3,col)])
                if v: return v, [(lin,col),(lin+1,col),(lin+2,col),(lin+3,col)]
        for lin in range(L - 3):
            for col in range(C - 3):
                v = ok([(lin,col),(lin+1,col+1),(lin+2,col+2),(lin+3,col+3)])
                if v: return v, [(lin,col),(lin+1,col+1),(lin+2,col+2),(lin+3,col+3)]
        for lin in range(3, L):
            for col in range(C - 3):
                v = ok([(lin,col),(lin-1,col+1),(lin-2,col+2),(lin-3,col+3)])
                if v: return v, [(lin,col),(lin-1,col+1),(lin-2,col+2),(lin-3,col+3)]
        return None, None

    def _c4_verificar_fim(self):
        v, cells = self._c4_linha_vencedora()
        if v:
            self.c4_fim = True
            self.c4_venc = cells
            self.c4_placar[v] += 1
            self._registrar_resultado(v, "P1")
            self._atualizar_placar_c4()
            nome = "Humano" if v == "P1" else "IA"
            self._dino_evento("c4", "p1_win" if v == "P1" else "p2_win")
            self._dino_evento("c4", "p2_lose" if v == "P1" else "p1_lose")
            self._tab_last_game = "Conect_4"
            self._tab_last_winner = v
            self.lbl_status_c4.config(text=f"{nome} venceu!", fg=self.c["vitoria"])
            self._rcon_async(f"say {nome} venceu o Conect 4!")
            self._log_jogo(f"Fim: {nome} venceu.", "ok")
            self._tab_update()
            self._c4_desenhar()
            return True
        if all(self.c4_grade[0][c] is not None for c in range(self.c4_cols)):
            self.c4_fim = True
            self._dino_evento("c4", "draw")
            self.c4_placar["Empate"] += 1
            self._registrar_resultado("Empate", "P1")
            self._atualizar_placar_c4()
            self.lbl_status_c4.config(text="Empate!", fg=self.c["subtexto"])
            self._tab_last_game = "Conect_4"
            self._tab_last_winner = "Empate"
            self._tab_update()
            self._rcon_async("say Empate no Conect 4!")
            return True
        return False

    def _atualizar_placar_c4(self):
        if not getattr(self, "lbl_c4_p1", None): return
        self.lbl_c4_p1.config(text=str(self.c4_placar["P1"]))
        self.lbl_c4_pe.config(text=str(self.c4_placar["Empate"]))
        self.lbl_c4_p2.config(text=str(self.c4_placar["P2"]))

    def _zerar_placar_c4(self):
        self.c4_placar = {"P1":0,"P2":0,"Empate":0}
        self._atualizar_placar_c4()

    def _c4_reiniciar(self):
        self._token_partida_c4 += 1
        self._inicio_partida = time.monotonic()
        self._sinal_final_c4_aplicado = False
        self.c4_grade = [[None]*self.c4_cols for _ in range(self.c4_lins)]
        self.c4_jogador = "P1"
        self.c4_jogadas = 0
        self.c4_fim = False
        self.c4_venc = None
        self.c4_pensando = False
        self._c4_simulando = False
        self._c4_grade_visual = None
        self._ultima_jogada_monotonic = 0.0
        self._c4_hover_col = self.c4_cols // 2
        self._c4_desenhar()
        self._atualizar_controle_jogador("conect4", "P1")
        self.lbl_status_c4.config(
            text=("Sua vez: analógico + SR ou clique numa coluna." if self.c4_modo == "ia" else "Jogador 1: analógico + SR ou clique numa coluna."),
            fg=self.c["x"]
        )
        self._tab_update()
        self._rcon_async("say Nova partida de Conect 4!")
        self._log_jogo("Conect 4 reiniciado. " + ("Modo IA." if self.c4_modo == "ia" else "Modo 2 jogadores."), "ok")

    def _atualizar_controle_jogador(self, jogo, jogador):
        """Mantém a saída de jogador ligada para X/P1 e desligada para O/P2."""
        try:
            cfg = self.config["controles_minecraft"]
            coord = cfg[jogo]["jogador"]
            ligado = jogador in ("X", "P1")
            bloco = cfg.get("bloco_ligado", "redstone_block") if ligado else cfg.get("bloco_desligado", "air")
            self._rcon_setblock(*coord, bloco, silencioso=True, forcar=True, assincrono=True)
        except Exception as e:
            self._log_jogo(f"Controle de jogador ({jogo}) falhou: {e}", "erro")

    def _acionar_reset_minecraft(self, jogo):
        """Único reset físico: redstone na coordenada configurada por aproximadamente 2s."""
        try:
            cfg = self.config["controles_minecraft"]
            coord = tuple(int(v) for v in cfg[jogo]["reset"])
            chave = ("reset", jogo)
            aid = self._temporizadores_blocos.pop(chave, None)
            if aid:
                try: self.root.after_cancel(aid)
                except Exception: pass
            ligado = cfg.get("bloco_ligado", "redstone_block")
            desligado = cfg.get("bloco_desligado", "air")
            self._rcon_setblock(*coord, ligado, silencioso=True, forcar=True)
            duracao = max(100, int(cfg.get("duracao_reset_ms", 2000)))
            self._temporizadores_blocos[chave] = self.root.after(
                duracao, lambda: self._finalizar_reset_minecraft(chave, coord, desligado))
        except Exception as e:
            self._log_jogo(f"Reset físico ({jogo}) falhou: {e}", "erro")

    def _finalizar_reset_minecraft(self, chave, coord, desligado):
        self._temporizadores_blocos.pop(chave, None)
        self._rcon_setblock(*coord, desligado, silencioso=True, forcar=True)

    def _novo_jogo_velha(self):
        self._velha_reiniciar()
        self._limpar_coordenadas_velha()
        self._acionar_reset_minecraft("velha")

    def _novo_jogo_c4(self):
        self._c4_reiniciar()
        self._limpar_coordenadas_c4()
        self._acionar_reset_minecraft("conect4")

    # ============================================================
    # SAIR
    # ============================================================
    def _fechar_rcon(self):
        try: self.mcr.disconnect()
        except Exception: pass

    def sair(self):
        self._encerrando = True
        try:
            if self._joycon_poll_id:
                self.root.after_cancel(self._joycon_poll_id)
        except Exception:
            pass
        try:
            self._joycon_reader.parar()
        except Exception:
            pass
        if getattr(self, "hotspot", None):
            self.hotspot.parar()
        for aid in (self._idle_id, self._conn_monitor_id, self._demo_id):
            if aid:
                try: self.root.after_cancel(aid)
                except Exception: pass
        for aid in list(self._temporizadores_blocos.values()):
            try: self.root.after_cancel(aid)
            except Exception: pass
        try: self._rcon_fila.put_nowait(None)
        except Exception: pass
        try:
            if self.mcr:
                threading.Thread(target=self._fechar_rcon, daemon=True).start()
        except Exception:
            pass
        try:
            salvar_config(self.config)
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.sair)
    root.mainloop()


if __name__ == "__main__":
    main()
