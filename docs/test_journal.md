# SysTrader 2-Week Test Journal

테스트 기간: 2026-04-20 ~ 약 2주. 실전 적용 전 알고리즘 강화 단계.
모든 수정/관찰은 시간순으로 누적 기록. 최종 분석 시 활용.

---

## 2026-04-20 (Day 1)

### 거래 결과 요약

| Trade | 종목 | 진입조건 | 매수가 | 매도가 | 수량 | 손익 | 비고 |
|---|---|---|---|---|---|---|---|
| 40 | 비아트론 (A141000) | price_breakout | 12,010 | 12,500 | 813 | **+4.08% (+398,370원)** | 보유 4초 |
| 43 | 현대지에프홀딩스 (A005440) | momentum | 14,363 | 14,010 | 697 | **-2.46% (-246,041원)** | 보유 66초 (시뮬 매도 지연) |
| 45 | 코세스 (A089890) | price_breakout | 33,537 | 33,950 | 118/298 | **+1.23% (+48,734원)** | 부분체결, 180주 orphan |

**손익 합계: +201,063원** (398,370 - 246,041 + 48,734)

### 식별된 패턴 (Day 1)

**timeout 다발 원인:**
- 거래량 적은 종목: tick=0 또는 매우 적음 (장 시작 전/장 마감 후 다수)
- consecutive_up=3 + buy_ratio≥0.6 동시 충족 어려움 (한국 주식 특성)
- 일반 한국어 단어 종목명(전방, 한화 등) substring false positive

**successful 패턴:**
- price_breakout: 누적 0.5% 상승 + ratio 0.55 (relax 후 0.3%/0.50)
- momentum: consecutive_up=3 + ratio=0.60
- 매수 직후 BPI 반전 시 즉시 매도(2초) → 짧은 익절 가능

### 적용한 코드 변경 (Day 1)

| 시간 | 파일 | 변경 |
|---|---|---|
| 09:42 | telegram_news.py | Ticker 패턴 `(NNNNNN)` 우선 추출 + 일반어 종목명 블랙리스트 (전방, 한화, 삼성 등) |
| 12:50 | worker.py / trading_engine.py | **Multi-condition entry**: momentum / price_breakout / volume_spike OR 조건 |
| 12:50 | database.py | `entry_condition` 컬럼 추가 |
| 14:48 | trading_engine.py | **부분체결 처리 강화**: SELLING 부분체결 시 cumulative 누적 + 잔여분 자동 SELL_MARKET 재발주 (2초 rate-limit), VWAP 기반 sell_price |
| 15:24 | worker.py / DB | 진입 임계값 완화: timeout 60→90s, breakout 0.5%/0.55 → 0.3%/0.50, vol_spike 2.0x/0.2% → 1.5x/0.1% |
| 15:24 | Dashboard.tsx | 거래내역 5초 주기 자동 갱신 + worker_state 이벤트 트리거 |

### 관찰된 버그/이슈 (Day 1)

1. **시뮬 매도 지연** — SELL_MARKET 발주 후 잔고 변경까지 1분+ (시뮬 호가 깊이 얕음)
2. **부분체결 orphan** — 코세스 180주 broker에 잔여 (Day 1 종료 시점). 자동 재발주 로직 추가했지만 그 거래는 이미 done 처리됨
3. **maxdrop 정상 동작 확인** — 한때 버그로 의심했으나 실제로는 +1.98% 후 -2.05% 하락 정상 추적

---

## 2026-04-21 (Day 2)

### 적용한 코드 변경

| 시간 | 파일 | 변경 |
|---|---|---|
| 05:45 | main.py | Holdings cache refresh 에러 rate-limit (CYBOS 점검 시간 로그 스팸 방지) |
| 09:00 | database.py / main.py / scripts/analyze_news.py | **키워드 학습 인프라**: `news_events` 테이블 추가, 모든 뉴스를 발생시점 가격과 함께 DB 저장. T+5/15/30분 시점 가격을 백그라운드에서 자동 스냅샷, 수익률 계산. 키워드별 분석 도구로 트리거/제외 후보 자동 추천 |
| 08:54 | code.py / cybos_news.py / telegram_news.py | **주권만 필터링**: CodeManager가 startup 시 GetStockSectionKind==1 (주권) 코드만 캐시. CYBOS 공시 + 텔레그램 추출 모두 주권만 통과. ETF/ETN/REIT/ELW/외국주 등 비매매 대상 제외 (4256→2719 주권). SectionKind 매핑 발견: 1=주권, 10=ETF, 17=ETN |
| 10:18 | trading_engine.py | **매수 부분체결 reconciliation**: HOLDING 상태에서 broker qty 추가 증가 감지 시 buy_qty/buy_price를 broker 평균가로 자동 보정. SGC에너지 케이스(8주 매수→184주 자동추가→192주 매도, -91,008원 손실) 같은 P&L 부정확 방지 |
| 11:42 | main.py / engine | **매수 잔여 자동 cancel**: 부분체결 첫 fill 감지 시 broker 미체결 잔여 즉시 cancel (CpTd0314 사용). buy_order_num을 worker에 저장하고 trading_engine이 cancel callback 호출. 추가체결 운빨 원천 차단 |
| 13:00 | database.py / main.py / scripts/analyze_postmortem.py | **매도 후 분석 인프라**: trades 테이블에 매도 후 5/15/30/60분 가격 + 1시간 내 max_price 자동 추적. 청산 사유별/진입 조건별 "missed gain" 분석 도구. 제테마 케이스(우리 +1.71% 청산 후 +20% 추가 상승)처럼 BPI 조기 청산 패턴 검증 가능 |
| 13:36 | worker.py / engine | **min_hold_sec=30 도입**: 매수 후 30초간 BPI/maxdrop sell 신호 무시 (stoploss는 항상 활성). 액스비스(2초만에 +0.11% 청산), 제테마(6초만에 +1.71% 청산) 같은 노이즈 청산 패턴 방지. 짧은 변동성 흡수하고 의미있는 추세 형성 후 청산 |
| 21:45 | worker.py / engine / DB | **매매 로직 Day 2 심층 개선**: BPI 0.4→0.3 (약한 반전만 청산), stoploss -3%→-5% (반등 기회), min_hold 30→60초, **trailing stop** 도입 (+1% 수익 달성 후 최고가 대비 -1.5% 시 청산, 기존 maxdrop_pct 대체). Day 2 분석 결과: BPI 조기 청산 8/10건, stoploss 후 +17% 반등(현대리바트), 총 기회손실 ~2.9M원 식별 |
| 22:10 | main.py / scripts/analyze_news.py | **API rate limit 보강 + 분석 강화**: polling 배치 20→5 (30초당 ~45 호출, 제한 60/15초 여유), 전수 뉴스 분석 스크립트 고도화 (by-source 통계, return distribution, "if bought every news" 시뮬, trigger/exclusion 자동 추천) |
| 23:00 | connection.py / Dashboard.tsx | **CYBOS auto-reconnect + 웹 실시간성 강화**: (1) CybosConnection COM 프록시 재-dispatch on failure — CYBOS 재로그인 시 자동 감지. (2) WebSocket cybos_status 메시지 프론트에서 handle, HTTP polling 의존 제거. (3) Page Visibility API — 탭 복귀 즉시 새로고침 (브라우저 1분 throttling 우회). 증상: CYBOS 재연결해도 웹 미연결 표시, 탭 오래 떠나면 로그 미반영 → 돌아오면 burst |
| 23:10 | routes/settings.py | **Settings 페이지 빈값 버그**: `/settings/config`가 PascalCase(appsettings.json 원형) 반환 vs 프론트는 snake_case 기대 → 값 미표시. `/settings/params`는 list 반환 vs 프론트는 dict 기대. GET은 변환하고 PUT은 역변환하여 일관성 확보 |
| 23:15 | bot.py / main.py / status.py | **알림 안정성 + 일일 요약**: (1) Markdown 전송 실패 시 plain text 자동 fallback — 종목명 특수문자로 인한 silent 실패 해결. (2) `send_daily_summary()` 메서드 추가: 총 손익/승률/최고·최저/전체 내역 표시. 매일 15:40 자동 + `POST /api/daily-summary` 수동. |
| 23:30 | trading_engine.py / executions.py / Analysis.tsx | **체결내역 정확도 + 차트 확장 + 재-sell 버그**: (1) 재-sell 로직 `current_qty>0` → `buy_qty - cumulative_sold_qty` 기준으로 수정 (기존 보유 있던 종목 "매도가능수량 부족" 에러 방지). (2) **CpTd5341 실제 체결내역 조회** 래퍼 (`CybosExecutions`) 추가, DONE 시 broker 데이터로 executions 테이블 교체 (float 추정치 → int 실제). (3) Analysis 차트에 매도 후 5m/15m/30m/1h 가격점 오버레이. |
| 23:50 | chart.py / trades.py / Analysis.tsx / trading_engine.py | **on-demand 차트 조회 + DB 용량 감축**: (1) `CpSysDib.StockChart` 래퍼(`CybosChart`) + `/trades/{id}/chart` 엔드포인트 (틱/1분/일봉, 200 bars). (2) Analysis에 "차트 가져오기" 버튼 + interval 선택. (3) worker `_ticks`는 메모리에서만 사용, DB `ticks.insert` 호출 제거 (장기 테스트 시 GB 단위 증가 방지). 기존 저장 틱은 유지되어 fallback 렌더링 가능. |
| 24:10 | routes/stats.py / Statistics.tsx | **Statistics 버그 2건**: (1) 일별 손익 그래프 마우스 오버 시 흰 배경 — recharts Tooltip cursor 기본값 대체 (`rgba(59,130,246,0.08)`). (2) 소스 선택 무동작 — `daily_stats` 테이블은 source 집계 없음. trades 테이블에서 news_source 필터로 on-demand 집계하여 summary/daily 재작성 |

## 2026-04-22 (Day 3)

### 적용한 코드 변경 (실전 매매 전 안전장치)

| 시간 | 파일 | 변경 |
|---|---|---|
| 13:00 | Dashboard.tsx | 손익 카드에 평균 수익률(%) 표시 (`+583,364 (+4.20%)`) |
| 13:10 | Dashboard.tsx | 뉴스포착/보유종목/오늘거래 테이블 자동 하단 스크롤 (새 항목 추가 시 즉시 보이도록). 뉴스는 시간순(오래된→최신) 정렬 |
| 14:00 | trading_engine.py | **15:15 매수 cutoff**: 15:15 이후 news_detected 도달해도 worker 생성 skip (`buy_cutoff_hhmm=1515` param). 장 마감 버퍼 확보 |
| 14:20 | trading_engine.py | **SELL 주문 3회 재시도 + backoff** (0.5s, 1s). 일시적 CYBOS/네트워크 오류 방어. SELL 실패 시 worker는 SELLING 유지 (cancel 금지) → `check_pending_fills`의 2초 주기 재시도 + 60초 selling_timeout 이중 안전망 |
| 14:25 | trading_engine.py | **Tick-less stoploss 안전망**: main loop에서 HOLDING worker 현재가 stock_mst 조회하여 -5% 넘으면 강제 청산 (`stoploss_tickless`). 거래량 적은 종목에서 tick 안 들어오는 동안 폭락해도 대응 |

### Day 3 적용 코드 변경 (장중 핫픽스)

| 시간 | 파일 | 변경 |
|---|---|---|
| 10:27 | trading_engine.py | **Re-sell 게이트 리셋**: SELLING 상태에서 부분체결 감지 시 `_last_resell_at` 갱신. 원 SELL_MARKET이 활발히 채워지는 동안 재발주 트리거 방지 (엠엑스온 케이스: 1086주 일괄 체결 직후 잔량 106주에 대해 재발주 → 매도가능수량 부족) |
| 11:13 | trading_engine.py | **Re-sell 간격 10s→30s, 실패 시 추가 30s backoff**: 모의투자에서 호가 부족으로 SELL_MARKET이 broker queue에 살아있는 동안 재발주 시 거부됨. selling_timeout(90s)이 최종 안전망 |
| 12:19 | balance.py | **CpTd6033 ret=1 (통신 일시 끊김) 재시도 추가**: 기존 ret=4 (rate limit)와 동일하게 0.3s·0.6s·0.9s backoff로 3회 재시도 |

### Day 3 거래 결과 (15건, 6승 8패 1even)

| Trade | 종목 | 진입조건 | 매도사유 | 손익% | 손익 | 비고 |
|---|---|---|---|---|---|---|
| 75 | 에스에너지 | (broker_reconcile) | overnight_liquidate | -4.44% | **-444,400원** | 전일 carry-over |
| 76 | 삼화전기 | volume_spike | bpi_reversal | +1.90% | +189,648원 | win |
| 77 | HJ중공업 | volume_spike | bpi_reversal | -2.03% | -203,992원 | 고점 매수 |
| 78 | 신성이엔지 | momentum | trailing_stop | 0.00% | 0원 | 매도 후 +8% 폭등 (놓침) |
| 79 | 앱클론 | price_breakout | bpi_reversal | +0.93% | +91,956원 | win |
| 80 | SK이터닉스 | price_breakout | bpi_reversal | -0.34% | -26,455원 | |
| 81 | 엠엑스온 | price_breakout | trailing_stop | -1.06% | -106,445원 | 60s 직후 |
| 82 | 아이에스티이 | momentum | trailing_stop | -2.85% | **-284,610원** | gain=+0.32%만 보고 진입 |
| 83 | 유라클 | price_breakout | bpi_reversal | +1.90% | +190,564원 | 매도 후 +6.74% 추가 |
| 84 | 아이씨디 | momentum | trailing_stop | -0.53% | -8,608원 | gain=-1.78%인데 momentum 진입 (버그) |
| 85 | 비에이치 | momentum | bpi_reversal | -0.21% | -21,128원 | |
| 86 | 달바글로벌 | price_breakout | bpi_reversal | -0.44% | -8,415원 | |
| 87 | 샌즈랩 | price_breakout | trailing_stop | +0.63% | +62,532원 | 60s 직후 |
| 89 | 그린광학 | momentum | trailing_stop | +1.55% | +154,780원 | 매도 후 +7.87% 추가 (놓침) |
| 90 | 엠오티 | momentum | trailing_stop | +1.10% | +110,448원 | 60s 직후 |

**Day 3 누적: -304,125원 (overnight 제외 +140,275원, 14건 6승 8패)**

### Day 3 Postmortem 분석

| 매도사유 | n | avg_actual | avg_if_held_to_max | 놓친 평균 |
|---|---|---|---|---|
| bpi_reversal | 7 | +0.24% | +2.82% | +2.57% |
| trailing_stop | 7 | -0.17% | +3.24% | +3.40% |
| overnight_liquidate | 3 | -2.03% | +2.44% | +4.48% |

| 진입조건 | n | win% | avg_actual | avg_if_max |
|---|---|---|---|---|
| momentum | 7 | 28.6% | -0.21% | +3.47% |
| price_breakout | 6 | 50.0% | +0.27% | +3.04% |
| volume_spike | 2 | 50.0% | -0.07% | +4.33% |

### Day 3 핵심 관찰

1. **trailing_stop이 60s 직후 트리거 빈번** (엠오티/샌즈랩/그린광학/엠엑스온/아이에스티이). +1% 활성화 후 peak에서 -1.5% 떨어지면 매도 — 평균 +3.24% 추가 상승 놓침.
2. **Momentum 진입 win% 28.6% (가장 약함)**. price_breakout 50%, volume_spike 50%. 특히 아이씨디는 gain=-1.78%인데 momentum 조건만으로 진입 → 진입 시점에 가격 하락 중. **momentum에 gain ≥ 0% 가드 필요**.
3. **price_breakout + bpi_reversal 조합 우수**: 유라클 +190K, 앱클론 +92K.
4. **재발주 핫픽스 효과**: 추가 "매도가능수량 부족" 발생 안 함.

### Day 4 (4/23) 테스트 변수 (1개만 격리)

- **`trailing_activate_pct: 0.01 → 1.0` (사실상 OFF)**: 급등주 스캘핑에 trailing이 안 맞을 수 있다는 가설 검증. Day 3 데이터에서 trailing -0.17% / BPI +0.24%로 BPI가 우월. trailing 적용 전 baseline (BPI 반전 + stoploss -5% + max_hold 300s) 으로 회귀해 승률 측정.
- 다른 파라미터 모두 유지.
- (참고) 처음엔 `0.02`로 활성화만 늦추는 안을 검토했으나, baseline과의 직접 비교가 더 명확한 신호를 준다고 판단해 OFF 선택.

### Day 4 결과 & 환경 이슈

- 완료 3건 **전부 loss**: 어보브반도체 -111K, 한국비엔씨 -42K, 오가노이드 -34K. **Total -188K**.
- 모두 BPI 또는 timeout 매도. Trailing OFF baseline 데이터로는 표본 부족.
- 환경 장애 지배적: CYBOS COM 하드 크래시 **5회** (4회 BUY BlockRequest + 1회 저녁 공시 flood의 PumpWaitingMessages). CYBOS Plus 완전 재시작 후 정상 복귀. 재로그인만으론 해결 안 됨 → CYBOS 내부 COM state 문제로 추정.
- 안정화 수정 (9 files, commit `ded69e2`): CommandQueue 위임, BUYING timeout, 장외 뉴스 필터(08:30-16:00), external supervisor, balance retry 통합, connection throttled redispatch.

### Day 5 (4/24) 변경 — 전체 기간 37건 분석 기반

**분석 결과 (누적 37건, 4/17~4/23)**:

| entry_condition | n | 승률 | avg_pnl | total |
|---|---|---|---|---|
| price_breakout | 21 | 52.4% | +0.49% | **+1,000K** |
| volume_spike | 4 | 50.0% | -0.00% | -0.5K |
| **momentum** | **9** | **33.3%** | **-0.18%** | **-316K** |

| sell_reason | n | 승률 | avg_pnl | missed_max |
|---|---|---|---|---|
| bpi_reversal | 24 | 54.2% | +0.54% | +2.15% |
| trailing_stop | 7 | 42.9% | -0.17% | +3.40% |
| overnight_liquidate | 3 | 0% | -2.03% | +4.48% |

| news_source | n | 승률 | avg_pnl | total |
|---|---|---|---|---|
| cybos (단일판매) | 8 | **62.5%** | +0.60% | +437K |
| telegram | 28 | 42.9% | +0.14% | +237K |

**변경 1건만 격리**:
- **`momentum` 진입 조건 제거** (`worker.py`). price_breakout과 volume_spike는 모두 `gain > 0` 을 요구하지만 momentum은 price-agnostic이어서 하락 중인 종목(예: 아이씨디 gain=-1.78%)에도 진입. 9건 중 승률 33%, 누적 -316K로 명백한 손실 기여자.
- trailing OFF는 유지 (데이터 추가 수집 필요).
- 향후 (Day 6+) 검토: 텔레그램 소스 필터 강화 (승률 42.9%), min_hold_sec 조정.

### Day 2 추가 거래

| Trade | 종목 | 진입조건 | 매수가 | 매도가 | 수량 | 손익 | 비고 |
|---|---|---|---|---|---|---|---|
| 64 | 액스비스 | price_breakout | 28,420 | ~28,450 | 352 | (selling timeout) | 매도 잔고감지 60초 timeout |
| 66 | STX엔진 | volume_spike | 53,147 | 53,300 | 188 | +28,764원 (+0.29%) | 7초 보유 |
| 65 | 한화엔진 | price_breakout | 58,451 | 58,900 | 109 | +48,941원 (+0.77%) | 부분체결 cancel 작동 |

### Day 2 추가 거래

| Trade | 종목 | 진입조건 | 매수가 | 매도가 | 수량 | 손익 | 비고 |
|---|---|---|---|---|---|---|---|
| 61 | 지엠비코리아 | price_breakout | 5,430 | 5,550 | 1848 | +221,760원 (+2.21%) | 깔끔 |
| 63 | 제테마 | price_breakout | 7,777 | 7,910 | 1039 | +138,187원 (+1.71%) | 매수잔여 cancel 정상작동 / 매도 후 +20% 추가상승 (조기청산 의심) |

### Day 2 거래 결과 (지금까지)

| Trade | 종목 | 진입조건 | 매수가 | 매도가 | 수량 | 손익 | 비고 |
|---|---|---|---|---|---|---|---|
| 53 | 아우토크립트 | price_breakout | 18,009 | 17,980 | 557 | -16,153원 | 슬리피지 큼 |
| 54 | 오가노이드사이언스 | price_breakout | 25,236 | 26,150 | 400 | **+365,600원 (+3.62%)** | 6초 |
| 55 | 솔트룩스 | price_breakout | 24,516 | 24,641 | 411 | +51,375원 | 부분체결 후 추가체결 운 좋음 |
| 56 | 삼성SDI | volume_spike | 592,934 | 592,000 | 16 | -14,944원 | 신규 vol 조건 첫 적중 |
| 58 | SGC에너지 | price_breakout | 51,674 | 51,200 | 192 | -91,008원 | 부분체결 후 자동추가, 손실 확대 |

**Day 2 누적: +294,870원 (5건 중 2승 3패)**

### 관찰된 패턴

(진행 중 — 시간 순으로 추가)

---

## 누적 미해결 이슈

- [ ] BUYING 회복 정확도 (DB에 buy_order_qty 저장은 됐지만 검증 미흡)
- [ ] CYBOS 점검 후 COM proxy stale → 재시작 필요 (자동 reconnect 미구현)
- [ ] 코세스 180주 orphan 정리 필요
- [ ] 진입 timeout 90초도 거래량 적은 종목엔 부족할 수 있음

## 우선순위 개선 영역 (이후 적용 검토)

1. **News quality scoring** — 뉴스 소스/카테고리별 historical 성공률 추적 → 가중치
2. **Entry confirmation delay** — 매수 직후 N초간 BPI 신호 무시 (조기 매도 방지)
3. **Trailing stop 개선** — 현재 maxdrop_pct 고정값, 수익률에 따라 동적 조정
4. **Position sizing** — 변동성 기반 베팅 금액 조정
5. **CYBOS auto-reconnect** — COM proxy 실패 시 자동 재dispatch
