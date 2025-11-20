import os
import shutil
import sys
import tempfile
import threading
import urllib.request
import webbrowser
import zipfile
from typing import List, Optional
import time

from flask import Flask, jsonify, render_template_string, request
from werkzeug.utils import secure_filename

import serial.tools.list_ports

from kflash import KFlash


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64MB bound
flash_lock = threading.Lock()
LOCAL_ONLY = {"127.0.0.1", "::1"}
KRUX_CACHE_DIR = os.path.join(os.path.dirname(__file__), "krux_cache")
_krux_lock = threading.Lock()
_krux_versions_cache = {"ts": 0, "data": []}

# Guard against python2
if sys.version_info < (3, 7):
    raise SystemExit("Python 3.7+ é obrigatório. Rode com `python3 web_flasher.py` ou `py -3 web_flasher.py`.")


HOME_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>K210 Web Flasher</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root {
      --bg-1: #050a14;
      --bg-2: #071426;
      --glow-1: rgba(79, 209, 197, 0.24);
      --glow-2: rgba(86, 130, 255, 0.2);
      --panel: rgba(255,255,255,0.04);
      --panel-strong: rgba(255,255,255,0.08);
      --accent: #4fd1c5;
      --accent-2: #7ea0ff;
      --text: #e9f3ff;
      --muted: #99a8b9;
      --danger: #f08c8c;
      --success: #7ae0a7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Space Grotesk", "Segoe UI", sans-serif;
      background: radial-gradient(120% 100% at 10% 20%, var(--glow-2), transparent 40%), radial-gradient(100% 90% at 80% 0%, var(--glow-1), transparent 30%), linear-gradient(180deg, var(--bg-1), var(--bg-2));
      color: var(--text);
      min-height: 100vh;
      padding: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .shell {
      width: 100%;
      max-width: 1100px;
      position: relative;
    }
    .blur-ball {
      position: absolute;
      width: 240px;
      height: 240px;
      background: radial-gradient(circle, var(--glow-1), transparent 60%);
      filter: blur(40px);
      opacity: 0.7;
      top: -60px;
      right: -60px;
      pointer-events: none;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--panel-strong);
      border-radius: 18px;
      padding: 26px;
      box-shadow: 0 30px 90px rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(8px);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-badge {
      width: 42px;
      height: 42px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      display: grid;
      place-items: center;
      color: #04101f;
      font-weight: 800;
      font-size: 18px;
      box-shadow: 0 10px 30px rgba(79, 209, 197, 0.35);
    }
    h1 {
      margin: 0;
      font-size: 26px;
      letter-spacing: -0.3px;
    }
    p.lead {
      margin: 0;
      color: var(--muted);
    }
    .cta {
      display: inline-flex;
      gap: 10px;
      align-items: center;
      background: linear-gradient(120deg, var(--accent), var(--accent-2));
      color: #04101f;
      border: none;
      border-radius: 12px;
      padding: 12px 16px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 12px 30px rgba(79, 209, 197, 0.25);
      transition: transform 0.1s ease, box-shadow 0.1s ease;
    }
    .cta:active { transform: translateY(1px); box-shadow: 0 8px 20px rgba(79, 209, 197, 0.18); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 18px;
      margin-top: 14px;
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.05);
      padding: 12px;
      border-radius: 12px;
    }
    label { font-size: 13px; color: var(--muted); }
    input, select {
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.02);
      color: var(--text);
      font-size: 14px;
      outline: none;
      transition: border 0.15s ease, box-shadow 0.15s ease;
    }
    option {
      background: #23263f;
    }
    input:focus, select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(84, 214, 197, 0.15);
    }
    .controls {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 10px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 12px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .pill input { width: auto; margin: 0; accent-color: var(--accent); }
    .muted { color: var(--muted); font-size: 13px; }
    .steps {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 10px;
      margin-top: 16px;
    }
    .step {
      padding: 12px;
      border-radius: 12px;
      background: rgba(255,255,255,0.03);
      border: 1px dashed rgba(255,255,255,0.08);
      color: var(--muted);
      font-size: 13px;
    }
    .status {
      margin-top: 10px;
      font-size: 14px;
      color: var(--muted);
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--muted);
      box-shadow: 0 0 0 0 rgba(79, 209, 197, 0.3);
      transition: background 0.2s ease;
    }
    .dot.active { background: var(--accent); }
    .dot.error { background: var(--danger); }
    pre {
      margin-top: 16px;
      background: rgba(0,0,0,0.4);
      border-radius: 14px;
      padding: 14px;
      color: #c6e6ff;
      max-height: 340px;
      overflow: auto;
      border: 1px solid rgba(255,255,255,0.06);
      font-family: ui-monospace, SFMono-Regular, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 13px;
    }
    .actions-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 14px;
    }
    .ghost-btn {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.08);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 10px;
      font-weight: 600;
      cursor: pointer;
      transition: border 0.15s ease, transform 0.1s ease;
    }
    .ghost-btn:hover { border-color: var(--accent); }
    .ghost-btn:active { transform: translateY(1px); }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.1);
      color: var(--text);
      font-size: 12px;
      font-weight: 600;
    }
    .inline-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .file-field { gap: 6px; }
    .file-trigger {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.05);
      color: var(--text);
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 10px 30px rgba(0,0,0,0.15);
      transition: border 0.12s ease, transform 0.1s ease;
    }
    .file-trigger:hover { border-color: var(--accent); }
    .file-trigger:active { transform: translateY(1px); }
    .file-name { color: var(--muted); font-size: 13px; min-height: 14px; }
    @media (max-width: 640px) {
      body { padding: 14px; }
      header { flex-direction: column; align-items: flex-start; }
      .actions-bar { flex-direction: column; align-items: stretch; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="blur-ball"></div>
    <div class="card">
      <header>
        <div class="brand">
          <div class="brand-badge">K</div>
          <div>
            <h1>K210 Web Flasher</h1>
            <p class="lead">Inspire-se no Jade Web Flasher: interface limpa, foco em segurança local (localhost).</p>
          </div>
        </div>
        <button type="button" class="cta" id="refresh">↻ Atualizar portas</button>
      </header>

      <div class="steps">
        <div class="step">1) Conecte a placa K210 via USB.</div>
        <div class="step">2) Escolha firmware e porta (ou use Auto).</div>
        <div class="step">3) Clique em "Flash firmware" e acompanhe os logs.</div>
      </div>

      <div class="field" style="margin-top:12px;">
        <div class="inline-actions" style="justify-content: space-between;">
          <div style="display:flex; align-items:center; gap:10px;">
            <div style="font-weight:700;">Krux Release from Github</div>
            <span class="badge" id="kruxBadge">Não baixado</span>
          </div>
          <button type="button" class="ghost-btn" id="kruxDownload">Baixar release</button>
        </div>
        <label for="kruxVersion">Versão</label>
        <input list="kruxVersions" id="kruxVersion" name="krux_version" value="v25.10.1" autocomplete="off" />
        <datalist id="kruxVersions"></datalist>
        <label for="kruxBoard">Placa (pasta do pacote Krux)</label>
        <select id="kruxBoard" name="krux_board">
          <option value="">Selecione após baixar o pacote</option>
        </select>
        <div class="controls" style="margin-top:6px;">
          <button type="button" class="cta" id="kruxFlash">Flash the Release →</button>
          <span class="muted" id="kruxInfo">Use este botão para baixar e flashear o firmware oficial do Github da Krux.</span>
        </div>
      </div>

      <form id="flashForm">
        <div class="grid">
          <div class="field">
            <div style="font-weight:700;">Arquivo firmware da Krux</div>
            <div class="field file-field">
              <button type="button" class="file-trigger" id="pickFile">Selecionar firmware</button>
              <span class="file-name" id="fileName"></span>
              <input type="file" id="firmware" name="firmware" accept=".bin,.kfpkg,.zip,.elf" required style="display:none">
            </div>
            <div class="field">
              <label for="port">Porta serial</label>
              <select id="port" name="port">
                <option value="auto">Auto (detectar)</option>
              </select>
              <span class="muted" id="portHint">Use "Auto" ou escolha uma COM específica.</span>
            </div>
            <div class="controls" style="margin-top:6px;">
              <button type="submit" class="cta">Flash arquivo firmware →</button>
              <span class="muted" id="kruxInfo">Use este botão para flashear o arquivo selecionado.</span>
            </div>
            
          </div>
        </div>

        <div class="actions-bar">
          <div class="status" id="status"><span class="dot" id="dot"></span><span id="statusText">Pronto.</span></div>
          <div style="display:flex; gap:10px;">
            <button type="reset" class="ghost-btn" id="clearLog">Limpar log</button>
          </div>
        </div>

        <pre id="log"></pre>
      </form>
    </div>
  </div>

  <script>
    const logEl = document.getElementById('log');
    const portSelect = document.getElementById('port');
    const refreshBtn = document.getElementById('refresh');
    const form = document.getElementById('flashForm');
    const statusText = document.getElementById('statusText');
    const dot = document.getElementById('dot');
    const clearLogBtn = document.getElementById('clearLog');
    const kruxDownloadBtn = document.getElementById('kruxDownload');
    const kruxFlashBtn = document.getElementById('kruxFlash');
    const kruxBoardSelect = document.getElementById('kruxBoard');
    const kruxInfo = document.getElementById('kruxInfo');
    const kruxBadge = document.getElementById('kruxBadge');
    const kruxVersionInput = document.getElementById('kruxVersion');
    const pickFileBtn = document.getElementById('pickFile');
    const fileInput = document.getElementById('firmware');
    const fileNameSpan = document.getElementById('fileName');
    async function loadPorts() {
      setStatus('Checando portas...', 'neutral');
      try {
        const res = await fetch('/api/ports');
        const data = await res.json();
        while (portSelect.options.length > 1) {
          portSelect.remove(1);
        }
        data.ports.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.device;
          opt.textContent = `${p.device} — ${p.description}`;
          portSelect.appendChild(opt);
        });
        setStatus(data.ports.length ? 'Portas atualizadas.' : 'Nenhuma porta encontrada.', data.ports.length ? 'ok' : 'neutral');
      } catch (err) {
        setStatus('Erro ao ler portas: ' + err, 'error');
      }
    }

    function setStatus(text, type) {
      statusText.textContent = text;
      dot.classList.remove('active', 'error');
      if (type === 'ok') dot.classList.add('active');
      if (type === 'error') dot.classList.add('error');
    }

    function renderKruxStatus(data) {
      const boards = data.boards || [];
      kruxBadge.textContent = data.extracted ? 'Pacote pronto' : (data.downloaded ? 'Baixado' : 'Não baixado');
      kruxBoardSelect.innerHTML = '';
      if (!boards.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Nenhuma placa encontrada — baixe o pacote Krux';
        kruxBoardSelect.appendChild(opt);
      } else {
        boards.forEach(b => {
          const opt = document.createElement('option');
          opt.value = b.id;
          opt.textContent = b.name;
          kruxBoardSelect.appendChild(opt);
        });
      }
      kruxFlashBtn.disabled = !boards.length;
      # kruxInfo.textContent = boards.length ? `Placas disponíveis: ${boards.map(b => b.name).join(', ')}` : 'Faça o download do pacote Krux para listar as placas.';
    }

    async function loadKruxStatus(version) {
      const ver = version || kruxVersionInput.value || 'v25.10.1';
      try {
        const res = await fetch(`/api/krux/status?version=${encodeURIComponent(ver)}`);
        const data = await res.json();
        if (!data.success) {
          kruxInfo.textContent = data.error || 'Erro ao consultar release Krux.';
          return;
        }
        renderKruxStatus(data);
      } catch (err) {
        kruxInfo.textContent = 'Erro ao consultar release Krux: ' + err;
      }
    }

    async function loadKruxVersions() {
      try {
        const res = await fetch('/api/krux/releases');
        const data = await res.json();
        if (!data.success) return;
        const versions = data.versions || [];
        const dl = document.getElementById('kruxVersions');
        dl.innerHTML = '';
        versions.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v;
          dl.appendChild(opt);
        });
        if (!kruxVersionInput.value && versions.length) {
          kruxVersionInput.value = versions[0];
        }
      } catch (err) {
        console.error('Erro ao carregar versões Krux', err);
      }
    }

    clearLogBtn.addEventListener('click', () => {
      logEl.textContent = '';
      setStatus('Pronto.', 'neutral');
    });

    pickFileBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
      fileNameSpan.textContent = fileInput.files.length ? fileInput.files[0].name : '';
    });

    refreshBtn.addEventListener('click', loadPorts);

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(form);
      setStatus('Flash em andamento...', 'ok');
      logEl.textContent = '';
      const controls = Array.from(form.elements);
      controls.forEach(el => el.disabled = true);
      try {
        const res = await fetch('/api/flash', { method: 'POST', body: formData });
        const data = await res.json();
        logEl.textContent = (data.log || []).join('\\n');
        setStatus(data.success ? 'Flash concluído.' : 'Falhou: ' + (data.error || 'veja o log'), data.success ? 'ok' : 'error');
      } catch (err) {
        setStatus('Erro inesperado: ' + err, 'error');
      } finally {
        controls.forEach(el => el.disabled = false);
      }
    });

    kruxDownloadBtn.addEventListener('click', async () => {
      setStatus('Baixando release Krux...', 'neutral');
      kruxDownloadBtn.disabled = true;
      try {
        const formData = new FormData();
        formData.append('version', kruxVersionInput.value || 'v25.10.1');
        const res = await fetch('/api/krux/download', { method: 'POST', body: formData });
        const data = await res.json();
        if (!data.success) {
          setStatus('Falha no download: ' + (data.error || 'erro desconhecido'), 'error');
        } else {
          setStatus(`Pacote Krux ${data.version} pronto.`, 'ok');
          renderKruxStatus(data);
        }
      } catch (err) {
        setStatus('Erro ao baixar Krux: ' + err, 'error');
      } finally {
        kruxDownloadBtn.disabled = false;
      }
    });

    kruxFlashBtn.addEventListener('click', async () => {
      const boardValue = kruxBoardSelect.value;
      if (!boardValue) {
        setStatus('Selecione uma placa Krux.', 'error');
        return;
      }
      const formData = new FormData();
      formData.append('krux_board', boardValue);
      formData.append('version', kruxVersionInput.value || 'v25.10.1');
      formData.append('port', portSelect.value);

      setStatus('Flash Krux em andamento...', 'ok');
      logEl.textContent = '';
      const controls = Array.from(form.elements).concat([kruxDownloadBtn, kruxFlashBtn, kruxBoardSelect]);
      controls.forEach(el => el.disabled = true);
      try {
        const res = await fetch('/api/flash-krux', { method: 'POST', body: formData });
        const data = await res.json();
        logEl.textContent = (data.log || []).join('\\n');
        setStatus(data.success ? 'Flash Krux concluído.' : 'Falhou: ' + (data.error || 'veja o log'), data.success ? 'ok' : 'error');
      } catch (err) {
        setStatus('Erro inesperado: ' + err, 'error');
      } finally {
        controls.forEach(el => el.disabled = false);
      }
    });

    window.addEventListener('load', loadPorts);
    window.addEventListener('load', () => loadKruxStatus());
    window.addEventListener('load', loadKruxVersions);
  </script>
</body>
</html>
"""


def parse_bool(value: str) -> bool:
    return str(value).lower() in {"1", "true", "on", "yes"}


def collect_ports():
    ports = []
    for info in serial.tools.list_ports.comports():
        ports.append(
            {
                "device": info.device,
                "description": info.description or "",
                "hwid": info.hwid,
            }
        )
    return ports


def ensure_local_only():
    return request.remote_addr in LOCAL_ONLY


def krux_paths(version: str) -> dict:
    safe_version = version.strip()
    if not safe_version.startswith("v"):
        safe_version = f"v{safe_version}"
    for ch in safe_version:
        if not (ch.isalnum() or ch in {".", "-", "_", "v"}):
            raise ValueError("Versão inválida.")
    zip_name = f"krux-{safe_version}.zip"
    url = f"https://github.com/selfcustody/krux/releases/download/{safe_version}/{zip_name}"
    root_dir = os.path.join(KRUX_CACHE_DIR, f"krux-{safe_version}")
    return {"version": safe_version, "zip_name": zip_name, "url": url, "root_dir": root_dir}


def get_krux_root_dir(version: str) -> Optional[str]:
    paths = krux_paths(version)
    root_dir = paths["root_dir"]
    if os.path.isdir(root_dir):
        return root_dir
    return None


def download_krux_release(version: str, force: bool = False) -> dict:
    paths = krux_paths(version)
    os.makedirs(KRUX_CACHE_DIR, exist_ok=True)
    zip_path = os.path.join(KRUX_CACHE_DIR, paths["zip_name"])
    if force and os.path.exists(zip_path):
        os.remove(zip_path)
    if not os.path.exists(zip_path):
        with urllib.request.urlopen(paths["url"]) as resp, open(zip_path, "wb") as f:
            shutil.copyfileobj(resp, f)
    root_dir = paths["root_dir"]
    if force and os.path.isdir(root_dir):
        shutil.rmtree(root_dir, ignore_errors=True)
    if not os.path.isdir(root_dir):
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(KRUX_CACHE_DIR)
    return {"zip_path": zip_path, "root_dir": root_dir, "version": paths["version"]}


def list_krux_boards(version: str) -> List[dict]:
    boards = []
    root = get_krux_root_dir(version)
    if not root:
        return boards
    for entry in os.listdir(root):
        board_dir = os.path.join(root, entry)
        if not os.path.isdir(board_dir):
            continue
        fw_path = os.path.join(board_dir, "firmware.bin")
        if os.path.isfile(fw_path):
            boards.append({"id": entry, "name": entry, "firmware": fw_path})
    boards.sort(key=lambda b: b["name"])
    return boards


def fetch_krux_versions(limit: int = 20) -> List[str]:
    now = time.time()
    # simple 5-minute cache
    if _krux_versions_cache["data"] and now - _krux_versions_cache["ts"] < 300:
        return _krux_versions_cache["data"]
    url = "https://api.github.com/repos/selfcustody/krux/releases?per_page=50"
    req = urllib.request.Request(url, headers={"User-Agent": "k210-web-flasher"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        # fallback to a static minimal list if network fails
        return ["v25.10.1", "v25.09.1", "v25.08.1", "v25.04.1"]
    versions = []
    for item in payload:
        tag = item.get("tag_name") or item.get("name")
        if not tag:
            continue
        if not tag.startswith("v"):
            continue
        versions.append(tag)
        if len(versions) >= limit:
            break
    if versions:
        _krux_versions_cache["data"] = versions
        _krux_versions_cache["ts"] = now
    return versions or ["v25.10.1"]


def run_kflash(firmware_path: str, port: str, board: str, baudrate: int, flash_type: int, sram: bool, noansi: bool) -> List[str]:
    logs: List[str] = []

    def capture(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "")
        message = sep.join(str(x) for x in args) + end
        logs.append(message.strip("\n"))
        # Mirror to server stdout for debugging
        print(message, end="")

    KFlash.print_callback = capture
    kf = KFlash(print_callback=capture)
    try:
        kf.process(
            terminal=False,
            dev=port,
            baudrate=baudrate,
            board=board or None,
            sram=sram,
            file=firmware_path,
            noansi=noansi,
            flash_type=flash_type,
        )
    except Exception as exc:  # noqa: BLE001
        exc._kflash_logs = list(logs)  # type: ignore[attr-defined]
        raise
    finally:
        KFlash.print_callback = None
    return logs


@app.route("/")
def index():
    return render_template_string(HOME_PAGE)


@app.route("/api/ports")
def api_ports():
    if not ensure_local_only():
        return jsonify({"success": False, "error": "Acesso permitido apenas a partir do host local."}), 403
    return jsonify({"ports": collect_ports()})


@app.route("/api/flash", methods=["POST"])
def api_flash():
    if not ensure_local_only():
        return jsonify({"success": False, "error": "Acesso permitido apenas a partir do host local."}), 403
    if not flash_lock.acquire(blocking=False):
        return jsonify({"success": False, "error": "Já existe um flash em andamento."}), 409

    firmware = request.files.get("firmware")
    if not firmware or firmware.filename == "":
        flash_lock.release()
        return jsonify({"success": False, "error": "Nenhum arquivo de firmware enviado."}), 400

    port = request.form.get("port", "auto")
    board = request.form.get("board") or None
    baudrate = request.form.get("baudrate", "1500000")
    try:
        flash_type = int(request.form.get("flash", "1"))
    except ValueError:
        flash_type = 1
    if flash_type not in (0, 1):
        flash_type = 1
    sram = parse_bool(request.form.get("sram", "false"))
    noansi = parse_bool(request.form.get("noansi", "true"))

    try:
        baudrate_val = int(baudrate)
    except ValueError:
        flash_lock.release()
        return jsonify({"success": False, "error": "Baudrate inválido."}), 400

    port_value = "DEFAULT" if port in ("auto", "", None) else port

    tmpdir = tempfile.mkdtemp(prefix="k210_webflash_")
    firmware_path = os.path.join(tmpdir, secure_filename(firmware.filename))
    firmware.save(firmware_path)

    try:
        logs = run_kflash(
            firmware_path=firmware_path,
            port=port_value,
            board=board,
            baudrate=baudrate_val,
            flash_type=flash_type,
            sram=sram,
            noansi=noansi,
        )
        success = True
        error = None
    except Exception as exc:  # noqa: BLE001
        logs = getattr(exc, "_kflash_logs", [])
        error = str(exc)
        success = False
    finally:
        flash_lock.release()
        shutil.rmtree(tmpdir, ignore_errors=True)

    if error:
        logs.append(f"ERROR: {error}")

    return jsonify({"success": success, "error": error, "log": logs})


@app.route("/api/krux/status")
def api_krux_status():
    if not ensure_local_only():
        return jsonify({"success": False, "error": "Acesso permitido apenas a partir do host local."}), 403
    version = request.args.get("version", "v25.10.1")
    try:
        paths = krux_paths(version)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)})
    zip_path = os.path.join(KRUX_CACHE_DIR, paths["zip_name"])
    downloaded = os.path.exists(zip_path)
    extracted = bool(get_krux_root_dir(version))
    boards = list_krux_boards(version) if extracted else []
    return jsonify({"success": True, "version": paths["version"], "downloaded": downloaded, "extracted": extracted, "boards": boards})


@app.route("/api/krux/releases")
def api_krux_releases():
    if not ensure_local_only():
        return jsonify({"success": False, "error": "Acesso permitido apenas a partir do host local."}), 403
    versions = fetch_krux_versions()
    return jsonify({"success": True, "versions": versions})


@app.route("/api/krux/download", methods=["POST"])
def api_krux_download():
    if not ensure_local_only():
        return jsonify({"success": False, "error": "Acesso permitido apenas a partir do host local."}), 403
    if not _krux_lock.acquire(blocking=False):
        return jsonify({"success": False, "error": "Download já em andamento."}), 409
    version = request.form.get("version", "v25.10.1")
    try:
        result = download_krux_release(version=version, force=False)
        boards = list_krux_boards(version)
        return jsonify({"success": True, "version": result["version"], "boards": boards})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": str(exc)})
    finally:
        _krux_lock.release()


@app.route("/api/flash-krux", methods=["POST"])
def api_flash_krux():
    if not ensure_local_only():
        return jsonify({"success": False, "error": "Acesso permitido apenas a partir do host local."}), 403
    if not flash_lock.acquire(blocking=False):
        return jsonify({"success": False, "error": "Já existe um flash em andamento."}), 409

    version = request.form.get("version", "v25.10.1")
    board_id = request.form.get("krux_board")
    if not board_id:
        flash_lock.release()
        return jsonify({"success": False, "error": "Nenhuma placa Krux selecionada."}), 400

    try:
        download_krux_release(version=version, force=False)
    except Exception as exc:  # noqa: BLE001
        flash_lock.release()
        return jsonify({"success": False, "error": f"Falha ao baixar release Krux: {exc}"}), 500

    board_entry: Optional[dict] = next((b for b in list_krux_boards(version) if b["id"] == board_id), None)
    if not board_entry:
        flash_lock.release()
        return jsonify({"success": False, "error": "Placa Krux não encontrada na release baixada."}), 404

    port = request.form.get("port", "auto")
    kboard = request.form.get("board") or None
    baudrate = request.form.get("baudrate", "1500000")
    try:
        baudrate_val = int(baudrate)
    except ValueError:
        flash_lock.release()
        return jsonify({"success": False, "error": "Baudrate inválido."}), 400

    try:
        flash_type = int(request.form.get("flash", "1"))
    except ValueError:
        flash_type = 1
    if flash_type not in (0, 1):
        flash_type = 1
    sram = parse_bool(request.form.get("sram", "false"))
    noansi = parse_bool(request.form.get("noansi", "true"))

    port_value = "DEFAULT" if port in ("auto", "", None) else port

    logs: List[str] = []
    error = None
    try:
        logs = run_kflash(
            firmware_path=board_entry["firmware"],
            port=port_value,
            board=kboard,
            baudrate=baudrate_val,
            flash_type=flash_type,
            sram=sram,
            noansi=noansi,
        )
        success = True
    except Exception as exc:  # noqa: BLE001
        logs = getattr(exc, "_kflash_logs", []) if hasattr(exc, "_kflash_logs") else logs
        error = str(exc)
        success = False
    finally:
        flash_lock.release()

    if error:
        logs.append(f"ERROR: {error}")

    return jsonify({"success": success, "error": error, "log": logs, "krux_board": board_id, "version": version})


if __name__ == "__main__":
    port = int(os.environ.get("KFLASH_WEB_PORT", "8000"))
    host = "127.0.0.1"
    url = f"http://{host}:{port}"
    print(f"\nK210 Web Flasher ouvindo em {url} (Ctrl+C para sair)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host=host, port=port, debug=False)
