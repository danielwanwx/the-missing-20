"""Actual browser decoder + live ERP read, using disclosed optical fixtures.

The generated QR/video is test input, not a real camera or newly received stock.
No inventory, invoice, quality or external notification write is requested.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from PIL import Image

from scripts.run_decision_workspace_smoke import _CDPBrowser, _chrome, _wait_ui

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/audits/2026-09-08-barcode-browser"
FIXTURE = "https://raw.githubusercontent.com/zxing/zxing/master/core/src/test/resources/blackbox/ean13-1/1.png"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with urlopen(FIXTURE, timeout=20) as response:
        raw = response.read(2_000_000)
    source = Image.open(BytesIO(raw)).convert("RGBA")
    matrix = json.loads(
        subprocess.check_output(
            [
                "node",
                "-e",
                "const {QRCodeWriter,BarcodeFormat}=require('@zxing/library');"
                "const m=new QRCodeWriter().encode('M20-CARTON-001',"
                "BarcodeFormat.QR_CODE,300,300,new Map());"
                "console.log(JSON.stringify(Array.from({length:300},(_,y)=>"
                "Array.from({length:300},(_,x)=>m.get(x,y)?1:0))));",
            ],
            cwd=ROOT,
        )
    )
    with (
        TemporaryDirectory(prefix="m20-barcode-browser-") as profile,
        _CDPBrowser(_chrome(), Path(profile)) as browser,
    ):
        browser.navigate("http://127.0.0.1:8893/?view=dashboard&review=barcode")
        _wait_ui(browser, "Boolean(window.M20Barcode)", "barcode module")
        browser.evaluate("""new Promise((resolve,reject)=>{const s=document.createElement('script');
            s.src='/vendor/zxing-browser.min.js';s.onload=resolve;s.onerror=reject;
            document.head.append(s);})""")
        browser.evaluate(
            "window.fixture = document.createElement('canvas'); document.body.append(fixture);"
        )
        browser.evaluate(f"""fixture.width={source.width}; fixture.height={source.height};
            const rgba={json.dumps(list(source.tobytes()))};
            fixture.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(rgba),
            {source.width},{source.height}),0,0);""")
        optical = browser.evaluate("""(async()=>{const decode=await M20Barcode.decoder();
            const original=await decode(fixture); const rotated=document.createElement('canvas');
            rotated.width=fixture.height;rotated.height=fixture.width;
            const c=rotated.getContext('2d');
            c.translate(rotated.width,0);c.rotate(Math.PI/2);c.drawImage(fixture,0,0);
            const blank=document.createElement('canvas');blank.width=300;blank.height=300;
            blank.getContext('2d').fillRect(0,0,300,300);
            return {original,rotated:await decode(rotated),blank:await decode(blank)};
            })()""")
        assert optical["original"][0]["rawValue"] == "8413000065504", optical
        assert optical["rotated"][0]["rawValue"] == "8413000065504", optical
        assert optical["blank"] == [], optical
        browser.evaluate(f"""fixture.width=300;fixture.height=300;
            const pixels={json.dumps(matrix)};const ctx=fixture.getContext('2d');
            ctx.fillStyle='white';ctx.fillRect(0,0,300,300);
            ctx.fillStyle='black';pixels.forEach((row,y)=>row.forEach((v,x)=>{{if(v)ctx.fillRect(x,y,1,1);}}));""")
        qr = browser.evaluate("(async()=>await (await M20Barcode.decoder())(fixture))()")
        assert qr[0] == {"rawValue": "M20-CARTON-001", "format": "qr_code"}, qr
        matched = browser.evaluate("""(async()=>{
            const code=(await (await M20Barcode.decoder())(fixture))[0];
            const r=await fetch('/api/v1/photo-receiving/barcode',{method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({arrival_id:'ARRIVAL-01',code:code.rawValue,format:code.format})});
            if(!r.ok)throw Error('ERP lookup '+r.status);return r.json();})()""")
        assert matched["unit_price"] == 50 and matched["inventory_changed"] is False
        # Encode actual local video bytes, then let the shipped capture controller
        # decode those frames. This is not mocked decoder output.
        browser.evaluate("""window.videoTest={codes:[],states:[]};
            window.testVideo=document.createElement('video');
            testVideo.muted=true;testVideo.playsInline=true;document.body.append(testVideo);
            window.testCapture=new M20Barcode.BarcodeCapture({video:testVideo,
            onCode:async(code,format,method)=>videoTest.codes.push({code,format,method}),
            onState:(state)=>videoTest.states.push(state)});""")
        browser.evaluate("""(async()=>{const stream=fixture.captureStream(10);
            const recorder=new MediaRecorder(stream,{mimeType:'video/webm'});
            const chunks=[];const done=new Promise(resolve=>{
            recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=resolve;});
            recorder.start();
            let frame=0;const redraw=setInterval(()=>{const c=fixture.getContext('2d');
            c.fillStyle=(frame++%2)?'white':'#eeeeee';c.fillRect(0,0,2,2);},100);
            await new Promise(r=>setTimeout(r,1200));clearInterval(redraw);
            recorder.stop();await done;
            stream.getTracks().forEach(t=>t.stop());
            await testCapture.start(new File(chunks,'synthetic-qr.webm',{type:'video/webm'}));
            })()""")
        try:
            _wait_ui(
                browser, "videoTest.states.includes('Video finished')", "video EOF", timeout=15
            )
        except AssertionError:
            print(
                browser.evaluate(
                    "({result:videoTest,time:testVideo.currentTime,"
                    "duration:testVideo.duration,error:testVideo.error?.message})"
                )
            )
            raise
        video_result = browser.evaluate("videoTest")
        assert video_result["codes"] == [
            {"code": "M20-CARTON-001", "format": "qr_code", "method": "video"}
        ], video_result
        browser.evaluate(
            "fixture.remove();testVideo.remove();document.getElementById('photo-receiving-open').click()"
        )
        _wait_ui(
            browser,
            "document.querySelector('.photo-receiving-dialog')?.open && "
            "document.querySelector('.receiving-scan') && "
            "!document.querySelector('.receiving-scan').hidden",
            "scan drawer",
        )
        _wait_ui(
            browser,
            "!document.querySelector('.receiving-scan-controls button').disabled",
            "receiving task ready",
        )
        browser.evaluate(
            "document.querySelector('.receiving-scan').open=true; "
            "document.querySelector('.receiving-scan input[type=text]').value='M20-CARTON-001';"
            "document.querySelector('.receiving-scan-controls button').click()"
        )
        _wait_ui(
            browser,
            "document.querySelector('.receiving-scan-result').textContent.includes('50 USD')",
            "ERP identity in UI",
        )
        browser.screenshot(OUT / "live-erp-barcode-drawer.png")
        evidence = {
            "at": datetime.now(UTC).isoformat(),
            "fixture": FIXTURE,
            "fixture_sha256": hashlib.sha256(raw).hexdigest(),
            "optical": optical,
            "qr": qr,
            "synthetic_video": video_result,
            "erp_read": matched,
            "camera_hardware_tested": False,
            "stock_write_requested": False,
            "console_errors": browser.console_errors(),
        }
        (OUT / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "optical": "PASS",
                    "synthetic_video": "PASS",
                    "erp_identity": "PASS",
                    "artifact": str(OUT),
                }
            )
        )


if __name__ == "__main__":
    main()
