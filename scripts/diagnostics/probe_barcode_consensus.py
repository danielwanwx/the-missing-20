"""Diagnose orientation disagreement in original UPC fixtures, without stock effects."""

import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_decision_workspace_smoke import _CDPBrowser, _chrome, _wait_ui

ROOT = Path(__file__).resolve().parents[2]


def main():
    with (
        TemporaryDirectory(prefix="m20-optical-probe-") as profile,
        _CDPBrowser(_chrome(), Path(profile)) as browser,
    ):
        browser.navigate("http://127.0.0.1:8893/?view=dashboard")
        _wait_ui(browser, "Boolean(window.M20Barcode)", "decoder")
        browser.evaluate("(async()=>{await M20Barcode.decoder();})()")
        for filename in ["upca-1-1.png", "upca-1-4.png", "ean13-1-1.png"]:
            code = base64.b64encode(
                (ROOT / "artifacts/fixtures/realistic-receiving-v1" / filename).read_bytes()
            ).decode()
            print(
                filename,
                browser.evaluate(
                    """(async()=>{
                const bytes=Uint8Array.from(atob("""
                    + json.dumps(code)
                    + """),c=>c.charCodeAt(0));
                const img=await createImageBitmap(new Blob([bytes]));
                const hints=new Map([[2,[14,7,4,11]],[3,true]]);
                const reader=new ZXingBrowser.BrowserMultiFormatReader(hints);
                const results=[];
                for(const turn of [0,1,2,3]) {
                  const c=document.createElement('canvas');c.width=turn%2?img.height:img.width;
                  c.height=turn%2?img.width:img.height;
                  const x=c.getContext('2d');x.translate(c.width/2,c.height/2);
                  x.rotate(turn*Math.PI/2);x.drawImage(img,-img.width/2,-img.height/2);
                  try {const r=reader.decodeFromCanvas(c);results.push({turn,code:r.getText()});}
                  catch(e){results.push({turn,error:e.getKind?.()||e.name});}
                }img.close();return results;
                })()"""
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
