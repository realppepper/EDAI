// SVG 회로도를 PNG 로 바꾼다 (make_schematic_svg.py 가 부른다). 흰 배경, 2배 크기.
// 사용법: node svg_to_png.js <in.svg> <out.png>   (NODE_PATH 에 @resvg/resvg-js 가 있는 node_modules)
const fs = require("fs");
const { Resvg } = require("@resvg/resvg-js");
const [input, output] = process.argv.slice(2);
const resvg = new Resvg(fs.readFileSync(input), { background: "white", fitTo: { mode: "zoom", value: 2 } });
fs.writeFileSync(output, resvg.render().asPng());
