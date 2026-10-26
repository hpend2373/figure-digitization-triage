/* 축·계열 확인 페이지에서 들어온 답 파일을, 그 페이지의 제안에서 이 저장소의 논리가 다시 짓는 줄과 대 봅니다.
 *
 *     node axis_series_recheck.mjs PAGE.html ANSWERS.csv
 *
 * 페이지에 실린 제안(DATA)을 꺼내 `axis_series_page.js`의 `recheck`에 넘깁니다. 관문 줄은 이 checkout의
 * `geometry_page.js`·`identity_page.js`가 다시 짓습니다 - 다른 판으로 지은 페이지라면 그 판의 줄과 다를 수
 * 있으니, 그때는 페이지를 지금 판으로 다시 지어 대 봅니다. 결과는 JSON 한 줄이고, 다른 줄·모르는 패널이
 * 하나라도 있으면 종료 코드 1입니다. 답하지 않은 패널과 이름은 보이기만 합니다(이름이 등록부와 맞는지는
 * `route_axis_series.py route --reviewers`가 봅니다). 아무 파일도 쓰지 않습니다.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const GEO = require(path.join(HERE, 'geometry_page.js'));
const IDN = require(path.join(HERE, 'identity_page.js'));
const AX = require(path.join(HERE, 'axis_series_page.js'));

export function pageData(html) {
  const head = 'var DATA = ', i = html.indexOf(head);
  if (i < 0) throw new Error('페이지에 DATA가 없습니다 - axis_series_page.py가 지은 페이지가 맞습니까?');
  const j = html.indexOf(';\nvar GEO = ', i);
  if (j < 0) throw new Error('DATA의 끝을 찾지 못했습니다');
  return JSON.parse(html.slice(i + head.length, j));
}

export function parseCsv(text) {
  text = text.replace(/^﻿/, '');
  const rows = []; let row = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(f); f = ''; }
    else if (c === '\n') { row.push(f.replace(/\r$/, '')); rows.push(row); row = []; f = ''; }
    else f += c;
  }
  if (f !== '' || row.length) { row.push(f.replace(/\r$/, '')); rows.push(row); }
  const head = rows.shift() || [];
  return rows.filter(r => r.length > 1).map(r => Object.fromEntries(head.map((h, k) => [h, r[k] === undefined ? '' : r[k]])));
}

export function main(argv) {
  if (argv.length !== 2) { console.error('쓰는 법: node axis_series_recheck.mjs PAGE.html ANSWERS.csv'); return 2; }
  let data;
  try { data = pageData(fs.readFileSync(argv[0], 'utf8')); } catch (e) { console.error(e.message); return 2; }
  const out = AX.recheck(GEO, IDN, data, parseCsv(fs.readFileSync(argv[1], 'utf8')));
  console.log(JSON.stringify({ rows: out.rows, same: out.same, differ: out.differ.length, unknown: out.unknown,
                               unanswered: out.unanswered.length, names: out.names }));
  for (const d of out.differ.slice(0, 20)) console.log('DIFFER ' + d.join(' | '));
  return out.differ.length || out.unknown.length ? 1 : 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main(process.argv.slice(2)));
}
