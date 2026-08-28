# figure-digitization-triage — 세션 인계 컨텍스트

> 코드는 전부 GitHub에 있습니다. 이 문서는 **코드가 아닌 것** — 로컬 자산의 위치,
> 테스트하는 법, 그리고 이 프로젝트가 무엇을 하려는지 — 만 담습니다.

---

## 1. 목표

우주비행·두부하향 침상안정(head-down bed rest)에서의 심혈관 반응에 대한 **체계적 문헌고찰**을
위한, 재현 가능한 **그림 디지타이즈 + QC 시스템**.

figure-level worklist: **116개 논문, 637개 figure 행**, 이 중 **95개 논문 / 353개 figure**가
디지타이즈 대상. 포함된 연구 상당수가 결과를 **그림으로만** 보고하기 때문에 숫자를 그림에서
읽어내야 하고 — 그림에서 읽은 숫자는 **그것을 만든 파이프라인이 자기가 무엇을 했는지 정확히
말할 수 있을 때만** 쓸 수 있습니다.

그래서 설계의 중심은 "얼마나 많이 읽느냐"가 아니라 **fail-closed**입니다:

- 근거가 없으면 **거절**한다. 그럴듯한 숫자를 잘못된 제목 아래 두는 것이 값이 없는 것보다 나쁘다.
- 모든 값은 **provenance tier(R0~R4)** 로 가격이 매겨지고, 등록되지 않은 방법은 최고 tier(=사용 불가).
- 모든 측정은 **되돌려서 확인**된다. 고친 것은 되돌려 스위트를 다시 돌린다.
  **고치기 전후로 똑같이 통과하는 테스트는 장식이고, 관측되지 않는 guard도 장식이라 지운다.**
- 통과시키려고 **상수를 넓히지 않는다.**
- scipy 없이 NumPy로 통계를 직접 구현한다.

### 에이전트가 절대 하지 않는 것 (PILOT.md 규칙)

reviewer 이름/ORCID/inspection date/registration date, `HUMAN_CONFIRMED`, panel 승인,
cell REJECTED — **전부 사람만**. 에이전트는 `DEMO_ONLY`에서 멈춥니다.
증명·판단·확인·거부를 대신하지 않습니다.

### 문서 규칙

- 숫자는 한 곳에만: README의 `CURRENT_SCENARIO_COUNT_CORE/FULL/RASTER_ONLY` 마커.
- INSTALL.md는 **릴리스 히스토리**이고, 일부러 현재 상태에 맞춰 다시 쓰지 않습니다.
- 예외 코드는 **데이터 타입별로만**. **논문별 예외 규칙은 만들지 않습니다.**
- 배포된 skill 폴더는 수정하지 않습니다 — 번들로 전달하고 사용자가 설치합니다.
- 답변은 **한국어**로.

---

## 2. 로컬 자산이 어디 있는가

### 2.1 코드 (영구, git)

| 무엇 | 어디 |
|---|---|
| 원격 | `https://github.com/hpend2373/figure-digitization-triage` (public) |
| Mac 클론 | `/Users/minyeop/Documents/figure-digitization-triage` (21 MB) |
| 컨테이너 작업본 | `/home/claude/geo/verify` — **휘발성**, 아래 방법으로 복원 |

컨테이너는 수시로 회수됩니다. 복원 절차:

```
# Mac에서
cd /Users/minyeop/Documents/figure-digitization-triage
git archive --format=tar.gz -o ~/Downloads/fdt_head.tar.gz HEAD
# → device_stage_files 로 컨테이너에 올린 뒤
mkdir -p /home/claude/geo/verify && cd /home/claude/geo/verify
tar -xzf /mnt/user-data/uploads/Downloads/fdt_head.tar.gz
```

### 2.2 코퍼스 — **git에도 Mac에도 없고, 이 컨테이너에만 있습니다**

배포 불가(non-redistributable) 자료라 저장소에 넣을 수 없습니다. 컨테이너가 회수되면
**사라집니다.** 다시 필요하면 사용자가 업로드해야 합니다.

| 파일 | 위치 | 크기/규모 |
|---|---|---|
| 그림 클립 | `/home/claude/geo/clips/` | 340개 PNG, 73개 논문, 61 MB |
| 그림 worklist | `/home/claude/geo/dig201.csv` | 201행 (pid, fig, axes, cells, target_axes, route_norm …) |
| 클립 인덱스 | `/home/claude/geo/clips201.csv` | 201행 |
| 캡션 스캔 | `captions.csv` | **없음**. `propose.py`에서 optional이라 없어도 돌아감 |
| 원본 PDF | 없음 | `/home/claude/geo/need_pdfs.txt`에 파일명 목록만 있음 |

클립 이름 규칙: `ID<pid>__fig<n>.png` (예: `ID464__fig2.png`).

### 2.3 출판사 래스터 — 이것도 컨테이너에만

| 위치 | 내용 |
|---|---|
| `/tmp/rg1` | 5.1 MB. `raster_root.RASTERS`가 SHA-256으로 핀한 12개 파일 + 옛 체크아웃 잔여물 |

핀된 12개: `323_p5_fig2.jpeg`, `397_fig1..5.jpeg`, `ID386_Fig2_publisher_898x1662.png`,
`fixtures/id323_fig1.jpeg`, `id323_fig1.tar`, `id323_fig2.tar`,
`clips/ID475__fig2.png`, `clips/ID349__fig3.png`.

**해시가 다르면 읽지 않고 거절합니다** — 한 렌더링에서 잰 좌표는 다른 렌더링에서
그럴듯하지만 틀린 숫자를 돌려주기 때문입니다.

### 2.4 컨테이너 작업본 세팅 (매 복원마다)

```
cd /home/claude/geo/verify
ln -sfn /home/claude/geo/clips clips
ln -sf  /home/claude/geo/dig201.csv   dig201.csv
ln -sf  /home/claude/geo/clips201.csv clips201.csv
```

---

## 3. 테스트하는 법

### 3.1 원칙

모든 테스트 파일은 **독립 실행 스크립트**입니다. pytest도, 수집도, 순서 의존도 없습니다.
exit 0이면 통과. 각 파일은 정확히 한 줄 `FDT_SCENARIOS_RUN=N`을 출력합니다.

```
python3 test_marker_routing.py        # 개별
for t in test_*.py; do python3 "$t"; done
```

### 3.2 두 개의 arm

| arm | 방법 | 무엇이 도는가 |
|---|---|---|
| 클론 arm | 환경변수 없이 | 저장소만으로 도는 것. 래스터 필요한 구간은 `FDT_RASTER_ABSENT` 토큰과 함께 SKIP |
| 래스터 arm | `FDT_RASTER_ROOT=/tmp/rg1` | 전부 |

프로파일은 별개 축입니다:

| 프로파일 | 차이 | 델타 |
|---|---|---|
| `core` | PDF 백엔드 없음 (poppler, pdfminer, pypdf 제거) | — |
| `full` | 백엔드 있음 | **+41** (`test_corpus_intake` +38, `test_tick_ocr` +3) |

이 컨테이너는 백엔드가 깔려 있으므로 **항상 `full`**입니다. core는 산술로 구합니다
(`full − 41`). 굳이 재보려면 `PYTHONPATH`에 import를 막는 `sitecustomize.py`를 두고
PATH에서 `pdftotext`를 뺍니다.

### 3.3 전체 스위트 러너 (27개)

```bash
set -e
: > /tmp/counts.tsv
for t in test_reproducibility test_kernel test_grid_engine \
         test_bar_reader test_mark_readers test_mono_bar \
         test_measure_mono_bars \
         test_integration test_run_batch test_finalize \
         test_compile_plan test_corpus_intake \
         test_geometry_proposer test_line_style_mono \
         test_documented_status test_provenance test_continuity \
         test_harness_compare test_panel_geometry \
         test_gate_trace test_y_scale_group test_tick_ocr \
         test_visual_verification test_marker_routing \
         test_axis_grain test_scatter_points \
         test_mutate; do
  out="$(python3 "$t.py" 2>&1)" || { printf '%s\n' "$out" | tail -25; exit 1; }
  m="$(printf '%s\n' "$out" | sed -nE 's/^FDT_SCENARIOS_RUN=([0-9]+)$/\1/p')"
  s=""; printf '%s\n' "$out" | grep -q FDT_RASTER_ABSENT && s=RASTER_SKIPPED
  printf '%s.py\t%s\t%s\n' "$t" "$m" "$s" >> /tmp/counts.tsv
  echo "$t $m $s"
done
awk -F'\t' '{n+=$2} END {print "TOTAL", n}' /tmp/counts.tsv
```

전체 한 번에 **9~12분**. bash 도구는 2분에 끊기므로 `nohup ... &` 로 띄우고
`sleep 115` 로 나눠서 로그를 봅니다.

### 3.4 문서 숫자 검증 (이게 진짜 게이트)

```
python3 verify_documented_status.py --profile full --rasters absent  /tmp/counts.tsv README.md run_batch.py
python3 verify_documented_status.py --profile full --rasters present /tmp/counts.tsv README.md run_batch.py
```

README 마커를 고치지 않고 시나리오를 추가하면 여기서 빨간불이 납니다. **0은 그 스위트가
`FDT_RASTER_ABSENT`를 출력했을 때만 허용**됩니다.

### 3.5 현재 숫자 (커밋 `51cd5c6`)

```
CORE 3348   FULL 3389   RASTER_ONLY 286     래스터 포함: 3634 / 3675     27 suites
raster-only 내역: test_bar_reader 24, test_integration 17, test_compile_plan 198,
                  test_reproducibility 5, test_visual_verification 42
```

### 3.6 forward test / 워크드 예제 (스위트 루프 밖, CI는 따로 돌림)

```
crosscheck_id323  build_id323
forward_test_397_mono_bar  forward_test_127_mono_bar  forward_test_397_mono_geometry
forward_test_real_monochrome  forward_test_beckers_geometry  forward_test_beckers_dpi
forward_test_397_line_style  forward_test_397_line_geometry  forward_test_464_scatter
pilot_397  pilot_beckers
```

### 3.7 갤러리 (그림으로 확인)

`png/verify.py`가 G1~G8을 그립니다. 캡션이 한국어라 **Noto CJK가 필수**입니다
(`apt-get install fonts-noto-cjk`) — 없으면 `png/capt.py`가 패키지 이름을 대며 raise합니다.
DejaVu로 폴백하지 않습니다(두부 글자가 나오므로).

```
python3 -c "import sys; sys.path[:0]=['png','.']; import verify as V; print(V.routed_twin()['out'])"
```

`png/G*.png`는 `.gitignore` 대상입니다.

### 3.8 mutation 검증 (이 저장소의 핵심 습관)

새 guard를 넣었으면 **되돌려서 시나리오가 죽는지** 확인합니다:

```
cp *.py /tmp/rev/ ; (한 곳만 뒤집는다) ; cd /tmp/rev && python3 test_X.py
# 살아남으면(SURVIVED) 그 guard는 관측되지 않는 것이고, 지우거나 시나리오를 씁니다.
```

---

## 4. GitHub에 올리는 법 (컨테이너에 자격증명이 없음)

컨테이너는 push할 수 없습니다. 항상 Mac을 경유합니다:

1. 바뀐 파일만 tar: `tar -czf /tmp/round.tar.gz a.py b.py README.md ...`
2. `SendUserFile` → `device_commit_files` 로 `~/Downloads/round.tar.gz`
3. 커밋 메시지도 같은 방법으로 `~/Downloads/COMMITMSG.txt`
4. Mac에서 (osascript):
   ```
   cd /Users/minyeop/Documents/figure-digitization-triage
   tar -xzf ~/Downloads/round.tar.gz && git add -A
   git commit -F ~/Downloads/COMMITMSG.txt && git push origin main
   git update-ref refs/remotes/origin/main <새 SHA>      # 매번 필수
   ```
5. CI 확인: `/opt/homebrew/bin/gh run list --limit 1`, `gh run view <id>`

CI는 `suite`(core)와 `intake-full` 두 job. 래스터 시크릿
(`FDT_RASTER_SOURCE` / `FDT_RASTER_TOKEN`)은 **아직 설정되지 않았고**, 설정은 사용자만
할 수 있습니다. 없으면 래스터 구간은 SKIP되고 fork도 초록으로 통과합니다.

**사용자는 claude.ai artifact URL을 열 수 없습니다.** 결과물은 PNG/파일로
`SendUserFile` 하세요. "결과를 보여달라"는 요청은 터미널 출력이 아니라
**실제로 디지타이즈된 플롯**을 뜻합니다.

---

## 5. 지금 어디까지 와 있나

### 굴러가는 것

- **397**: 26 panel / 384 declared cell / 123 read / **0 accepted** — 이게 정답입니다
  (본문은 30분 평균 SEM, Fig 3/4 캡션은 3분 평균이라 SD/SEM이 논문에 없음 → 저자 문의 대기).
- **LINE_MONO_STYLE**: Fig 1·2의 두-검은-곡선 패널 12개 전부 읽힘. 독립 눈 판독 대비
  24셀 중 18셀이 50 mmHg 축에서 1.65 mmHg 이내, 나머지 6개는 거절(곡선이 한 덩어리인 지점).
- **Beckers 2007**: 표와 대조 가능한 ladder 완주. Attested면 10개 값 accept,
  Unattested면 `run_batch`가 자기 출력을 지우고 `DEMO_OUTPUT_REFUSED`.
- **twin-axis scatter**: `marker_routing` + `axis_grain` + `scatter_points`가
  파이프라인에 배선 완료. `axis_manifest.csv`(optional)가 스위치.
  fixture에서 11/22/33 px에 16·17·18개 라우팅, **오분류 0**.

### 열려 있는 결정 (사람이 답해야 하는 것)

1. **`marker_routing._split`의 최소 클래스 크기(전체의 1/4)** — 464 Fig. 2가 여기서 막힙니다.
   interior ink 분포의 가장 뚜렷한 절단이 25|6, index 2.702(필요값 2.0)인데
   6/31이 1/4 미만이라 규칙이 그 절단을 거부하고, 허용되는 최선이 24|7의 1.858입니다.
   **31개 중 6개짜리가 outlier인가, 그림이 실제로 그린 네 계열 중 작은 쪽인가.**
   이 결정이 나면 464가 양성 forward test가 됩니다. (`forward_test_464_scatter.py`가 측정 출력)
2. IQR→SD 변환 정책, 이중축 배정, dispersion 없는 셀 처리, ID475 Fig 6/7 이중 계수.
3. `source_document`의 page-range 정책, bivariate group summary 통계.
4. `main` 브랜치 보호 설정.

### 남은 작업 (사용자만 할 수 있는 것)

- **private raster 저장소 + CI 시크릿 2개** 설정.
- 참조되지 않는 객체 gc를 위한 GitHub Support 요청 (history purge 잔여).
- 등록된 사람 R2/R3 리뷰.

### 남은 작업 (에이전트가 할 수 있는 것)

- negative gold case: 475 Fig.1 `PANEL_TOPOLOGY_REVIEW_REQUIRED`,
  177 Fig.2 `Y_SCALE_GROUP_NO_PROVIDER`, merged cell NO_VALUE/R4.
- `pilot_323.py` + CI 배선, geometry_proposer를 plan 층에 연결.
- 전체 코퍼스(187 figure) 재측정.

---

## 6. 새 세션을 시작할 때 붙여넣을 문장

> 저장소는 `hpend2373/figure-digitization-triage`, Mac 클론은
> `/Users/minyeop/Documents/figure-digitization-triage`입니다. 컨테이너 작업본은
> `/home/claude/geo/verify`이고 회수되면 Mac HEAD에서 `git archive`로 복원합니다.
> 코퍼스(`/home/claude/geo/clips`, `dig201.csv`, `clips201.csv`)와 출판사 래스터
> (`/tmp/rg1`)는 배포 불가라 git에 없고 컨테이너에만 있습니다 — 없으면 관련 구간은
> SKIP됩니다. 테스트는 스위트 27개를 두 arm(래스터 유/무)으로 돌리고
> `verify_documented_status.py`로 README 숫자를 검증합니다. push는 컨테이너에서 못 하고
> Mac을 경유합니다. 답변은 한국어로, 에이전트는 어떤 attestation도 하지 않습니다.
