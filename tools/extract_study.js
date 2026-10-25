// Parse the cheat-sheet / FAQ object literals as data in an empty vm context.
const fs = require('fs'), path = require('path'), vm = require('vm');
const [dl, out] = process.argv.slice(2);
const pick = (pre) => path.join(dl, fs.readdirSync(dl).find(f => f.startsWith(pre)));
const lit = (s) => vm.runInNewContext('(' + s + ')', Object.create(null), { timeout: 1000 });
const res = {};
for (const cert of ['ccar-f', 'ccar-p']) {
  let src = fs.readFileSync(pick(cert + '-cheat-sheet-'), 'utf8');
  let i = src.indexOf('[{id:"instruction"'), j = src.indexOf('}}],C=', i) + 3;
  const cards = lit(src.slice(i, j).replace(/icon:[A-Za-z_$]+,/g, ''));
  src = fs.readFileSync(pick(cert + '-content-'), 'utf8');
  i = src.indexOf('[{q:'); j = src.indexOf('}]', i) + 2;
  const faq = lit(src.slice(i, j));
  res[cert] = { cheatsheet: cards, faq };
  console.log(cert, cards.length, 'cards', faq.length, 'faq');
}
fs.writeFileSync(out, JSON.stringify(res, null, 1));
