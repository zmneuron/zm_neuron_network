"""Render the repository workflow from Mermaid source with a local Mermaid bundle.

Requires Playwright and its Chromium, or --browser pointing to a Chromium browser.
The pinned Mermaid 11.17.2 bundle is supplied with --mermaid-js; no downloads occur.
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mermaid-js', type=Path, required=True)
    parser.add_argument('--browser', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = (root / 'overview.mmd').read_text(encoding='utf-8')
    with sync_playwright() as runtime:
        launch = {'headless': True}
        if args.browser:
            launch['executable_path'] = str(args.browser.resolve())
        browser = runtime.chromium.launch(**launch)
        page = browser.new_page(viewport={'width': 1600, 'height': 2200}, device_scale_factor=2)
        page.set_content('<html lang="zh-CN"><meta charset="utf-8"><style>'
                         'body{margin:0;background:#fffdf7}#diagram{padding:32px;display:inline-block}'
                         '</style><body><div id="diagram"></div></body></html>')
        page.add_script_tag(path=str(args.mermaid_js.resolve()))
        svg = page.evaluate('''async (source) => {
            mermaid.initialize({startOnLoad:false, securityLevel:'strict'});
            const {svg} = await mermaid.render('workflow', source);
            document.getElementById('diagram').innerHTML = svg;
            await document.fonts.ready;
            const element = document.querySelector('#diagram svg');
            element.style.background = '#fffdf7';
            const bounds = element.viewBox.baseVal;
            element.setAttribute('width', bounds.width);
            element.setAttribute('height', bounds.height);
            element.style.maxWidth = 'none';
            // Mermaid class colors otherwise override the pale hatching strokes.
            for (const path of element.querySelectorAll('.rough-node .label-container path')) {
                for (const attribute of ['stroke', 'fill']) {
                    if (path.hasAttribute(attribute))
                        path.style.setProperty(attribute, path.getAttribute(attribute), 'important');
                }
            }
            return new XMLSerializer().serializeToString(element);
        }''', source)
        # Explicit background keeps dark GitHub themes from changing figure contrast.
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        element = ET.fromstring(svg)
        (root / 'overview.svg').write_text(ET.tostring(element, encoding='unicode'), encoding='utf-8')
        page.locator('#diagram').screenshot(path=str(root / 'overview.png'))
        browser.close()
    print('Rendered overview.svg and overview.png from overview.mmd.')


if __name__ == '__main__':
    main()
