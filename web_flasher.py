import os
import shutil
import tempfile
import threading
import webbrowser
from typing import List

from flask import Flask, jsonify, render_template_string, request
from werkzeug.utils import secure_filename

import serial.tools.list_ports

from kflash import KFlash


app = Flask(__name__)
flash_lock = threading.Lock()


HOME_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>K210 Web Flasher</title>
  <style>
    :root {
      --bg: linear-gradient(145deg, #0a1f2f, #123d5a);
      --panel: #0c2436;
      --accent: #2dd4bf;
      --accent-2: #7cc0ff;
      --text: #e7f4ff;
      --muted: #8ba5b7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Space Grotesk", "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      width: 100%;
      max-width: 760px;
      background: var(--panel);
      border: 1px solid rgba(255,255,255,0.05);
      border-radius: 14px;
      padding: 24px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
    }
    h1 {
      margin: 0 0 12px;
      font-size: 26px;
      letter-spacing: -0.5px;
    }
    p.lead { margin: 0 0 24px; color: var(--muted); }
    label { display: block; margin-bottom: 6px; font-size: 13px; color: var(--muted); }
    input, select, button {
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.02);
      color: var(--text);
      font-size: 14px;
      outline: none;
    }
    input:focus, select:focus { border-color: var(--accent); }
    button {
      cursor: pointer;
      margin-top: 8px;
      background: linear-gradient(120deg, var(--accent), var(--accent-2));
      color: #0a1f2f;
      font-weight: 700;
      border: none;
      box-shadow: 0 10px 30px rgba(45, 212, 191, 0.25);
      transition: transform 0.1s ease, box-shadow 0.1s ease;
    }
    button:active { transform: translateY(1px); box-shadow: 0 6px 18px rgba(45, 212, 191, 0.2); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
    .row { margin-bottom: 14px; }
    .status { margin-top: 6px; font-size: 13px; color: var(--muted); }
    pre {
      margin-top: 14px;
      background: rgba(0,0,0,0.35);
      border-radius: 12px;
      padding: 14px;
      color: #c4f1f9;
      max-height: 320px;
      overflow: auto;
      border: 1px solid rgba(255,255,255,0.05);
    }
    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }
    .actions button {
      width: auto;
      padding-inline: 16px;
      margin: 0;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: rgba(255,255,255,0.06);
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      color: var(--muted);
      font-size: 13px;
    }
    .pill input { width: auto; margin: 0; }
  </style>
</head>
<body>
  <div class="card">
    <h1>K210 Web Flasher</h1>
    <p class="lead">Selecione o firmware, escolha a porta/placa e envie para o Kendryte K210 direto pelo navegador.</p>
    <form id="flashForm">
      <div class="row">
        <label for="firmware">Firmware (.bin ou .kfpkg)</label>
        <input type="file" id="firmware" name="firmware" accept=".bin,.kfpkg,.zip,.elf" required>
      </div>
      <div class="grid">
        <div class="row">
          <label for="port">Porta serial</label>
          <select id="port" name="port">
            <option value="auto">Auto (detectar)</option>
          </select>
          <div class="actions">
            <button type="button" id="refresh">Atualizar portas</button>
          </div>
        </div>
        <div class="row">
          <label for="board">Placa</label>
          <select id="board" name="board">
            <option value="">Auto</option>
            <option value="goE">Maix Go (openec)</option>
            <option value="goD">Maix Go (cmsis-dap)</option>
            <option value="dan">Sipeed Dan</option>
            <option value="bit">Maix Bit</option>
            <option value="bit_mic">Maix Bit (mic)</option>
            <option value="kd233">KD233</option>
            <option value="maixduino">Maixduino</option>
            <option value="trainer">K210 Trainer</option>
          </select>
        </div>
      </div>
      <div class="grid">
        <div class="row">
          <label for="baudrate">Baudrate</label>
          <input id="baudrate" name="baudrate" type="number" value="1500000" min="9600" step="1">
        </div>
        <div class="row">
          <label for="flashType">Tipo de flash</label>
          <select id="flashType" name="flash">
            <option value="1">SPI0 (padrão)</option>
            <option value="0">SPI3</option>
          </select>
        </div>
      </div>
      <div class="actions" style="margin-top: 8px;">
        <label class="pill"><input type="checkbox" id="sram" name="sram"> Carregar apenas em SRAM</label>
        <label class="pill"><input type="checkbox" id="noansi" name="noansi" checked> Desabilitar ANSI</label>
      </div>
      <button type="submit">Flash firmware</button>
      <div class="status" id="status">Pronto.</div>
      <pre id="log"></pre>
    </form>
  </div>
  <script>
    const statusEl = document.getElementById('status');
    const logEl = document.getElementById('log');
    const portSelect = document.getElementById('port');
    const refreshBtn = document.getElementById('refresh');
    const form = document.getElementById('flashForm');

    async function loadPorts() {
      statusEl.textContent = 'Checando portas...';
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
        statusEl.textContent = data.ports.length ? 'Portas atualizadas.' : 'Nenhuma porta encontrada.';
      } catch (err) {
        statusEl.textContent = 'Erro ao ler portas: ' + err;
      }
    }

    refreshBtn.addEventListener('click', loadPorts);

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(form);
      statusEl.textContent = 'Flash em andamento...';
      logEl.textContent = '';
      const controls = Array.from(form.elements);
      controls.forEach(el => el.disabled = true);
      try {
        const res = await fetch('/api/flash', { method: 'POST', body: formData });
        const data = await res.json();
        logEl.textContent = (data.log || []).join('\\n');
        statusEl.textContent = data.success ? 'Flash concluído.' : 'Falhou: ' + (data.error || 'veja o log');
      } catch (err) {
        statusEl.textContent = 'Erro inesperado: ' + err;
      } finally {
        controls.forEach(el => el.disabled = false);
      }
    });

    window.addEventListener('load', loadPorts);
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
    return jsonify({"ports": collect_ports()})


@app.route("/api/flash", methods=["POST"])
def api_flash():
    if not flash_lock.acquire(blocking=False):
        return jsonify({"success": False, "error": "Já existe um flash em andamento."}), 409

    firmware = request.files.get("firmware")
    if not firmware or firmware.filename == "":
        flash_lock.release()
        return jsonify({"success": False, "error": "Nenhum arquivo de firmware enviado."}), 400

    port = request.form.get("port", "auto")
    board = request.form.get("board") or None
    baudrate = request.form.get("baudrate", "115200")
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


if __name__ == "__main__":
    port = int(os.environ.get("KFLASH_WEB_PORT", "8000"))
    url = f"http://127.0.0.1:{port}"
    print(f"\nK210 Web Flasher ouvindo em {url} (Ctrl+C para sair)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host="0.0.0.0", port=port, debug=False)
