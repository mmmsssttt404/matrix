"""Real-browser smoke test using a separate workspace copied from real local data."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
workspace = ROOT / ".cache" / "browser-smoke" / str(uuid4())
workspace.mkdir(parents=True)
for name in ["prices.csv", "documents.csv"]:
    shutil.copy2(ROOT / "data" / name, workspace / name)
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
environment = dict(os.environ, MATRIX_DATA_DIR=str(workspace))
environment["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / ".cache" / "browsers")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = environment["PLAYWRIGHT_BROWSERS_PATH"]
log = (workspace / "server.log").open("w")
server = subprocess.Popen([str(ROOT / ".venv/bin/streamlit"), "run", str(ROOT / "app.py"),
                           "--server.port", str(port), "--server.headless", "true"],
                          cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
try:
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while True:
        try:
            with urlopen(url + "/_stcore/health", timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            if time.monotonic() > deadline:
                raise RuntimeError("Streamlit did not start; see " + str(workspace / "server.log"))
            time.sleep(.2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1050}, device_scale_factor=1)
        page.goto(url)
        expect(page.get_by_role("heading", name="让研究有依据，让风险可计算")).to_be_visible(timeout=30000)
        page.get_by_role("tab", name="02 公司研究").click()
        page.get_by_role("button", name="检索并保留依据", exact=True).click()
        expect(page.get_by_text("keyword_baseline", exact=False)).to_be_visible(timeout=30000)
        page.get_by_role("tab", name="03 矩阵与组合").click()
        page.get_by_role("button", name="计算矩阵与最小方差组合", exact=True).click()
        expect(page.get_by_text("年化波动率（样本内）", exact=True)).to_be_visible(timeout=30000)
        expect(page.locator('[data-testid="stMultiSelect"]').get_by_text("AAPL", exact=True)).to_be_visible()
        # Wait for the real Plotly canvas to finish its initial render.
        page.locator('[data-testid="stPlotlyChart"]:visible').first.wait_for()
        images = ROOT / "docs" / "images"
        images.mkdir(exist_ok=True)
        page.screenshot(path=str(images / "prototype.png"), full_page=True)
        page.get_by_role("tab", name="04 模拟交易").click()
        page.get_by_role("button", name="创建本地模拟账户", exact=True).click()
        expect(page.get_by_text("可用现金", exact=True)).to_be_visible(timeout=30000)
        page.get_by_role("button", name="提交并推进至下一交易日", exact=True).click()
        expect(page.get_by_text("成交已保存。", exact=True)).to_be_visible(timeout=30000)
        if page.locator('[data-testid="stException"]').count():
            raise RuntimeError("Streamlit displayed an exception")
        page.screenshot(path=str(images / "paper-trading.png"), full_page=True)
        browser.close()
    print(json.dumps({"passed": True, "workspace": str(workspace), "checks": ["keyword research", "matrix analysis", "create account", "next-open fill"], "screenshots": str(images)}, ensure_ascii=False))
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=5)
    log.close()
