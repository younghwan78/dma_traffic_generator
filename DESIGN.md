# DMA Traffic Generator 설계 문서

## 1. 목적

`dma_traffic_gen`은 멀티미디어 IP의 DMA request를 trace 형태로 생성하는 Python CLI 도구입니다.

이 도구가 모델링하는 것:
- DMA가 언제 request를 발행하는지
- 어떤 주소로 얼마나 큰 payload를 보내는지
- IP 간 OTF/M2M 연결에 따라 어떤 순서로 시작하는지

이 도구가 모델링하지 않는 것:
- Bus arbitration
- backpressure
- outstanding queue saturation
- IOMMU address translation
- RTL 수준의 세부 파이프라인

즉 현재 구현은 “trace generator”이며, Bus/NoC simulator의 입력을 만드는 역할에 집중합니다.

## 2. 현재 산출물

실행 결과는 기본적으로 아래 3개입니다.

- `traffic.txt`
- `summary.txt`
- `bw_plot.html`

시간 단위는 모두 `ns`입니다.

## 3. 상위 아키텍처

구조는 크게 5개 계층으로 나뉩니다.

### 3.1 Config 계층

역할:
- YAML 로드
- HW config / scenario config 검증
- 두 설정 merge
- OTF/M2M 링크 검증
- timing 기준 입력 포트 결정

주요 파일:
- `dma_traffic_gen/config/hw_schema.py`
- `dma_traffic_gen/config/scenario_schema.py`
- `dma_traffic_gen/config/loader.py`
- `dma_traffic_gen/config/yaml_io.py`

### 3.2 Format / Address 계층

역할:
- image format의 bpp 계산
- plane 분리
- SBWC 레이아웃 계산
- raster / tile 기반 주소 생성
- stat sample byte 계산

주요 파일:
- `dma_traffic_gen/formats.py`
- `dma_traffic_gen/address/pattern.py`
- `dma_traffic_gen/address/sbwc.py`

### 3.3 DMA 모델 계층

역할:
- type별 transaction 생성

주요 파일:
- `dma_traffic_gen/dma/base.py`
- `dma_traffic_gen/dma/image_dma.py`
- `dma_traffic_gen/dma/stat_dma.py`
- `dma_traffic_gen/dma/random_dma.py`

### 3.4 Scheduling 계층

역할:
- IP graph topological order 계산
- OTF start gate 처리
- M2M dependency 처리
- frame duration truncation
- global transaction ID 부여

주요 파일:
- `dma_traffic_gen/core/simulator.py`
- `dma_traffic_gen/core/transaction.py`
- `dma_traffic_gen/core/clock.py`

### 3.5 Output 계층

역할:
- `traffic.txt` 저장
- `summary.txt` 생성
- BW graph 생성
- trace 재요약 / 필터링

주요 파일:
- `dma_traffic_gen/output/writer.py`
- `dma_traffic_gen/output/summary.py`
- `dma_traffic_gen/output/graph.py`
- `dma_traffic_gen/cli.py`

## 4. 입력 모델

## 4.1 HW YAML

HW YAML은 IP 고유의 정적 정보를 담습니다.

예:
- `clock_mhz`
- `ports`
- `dmas`
- `bus_width_byte`
- `ppc`
- `xiu_port`
- `pattern`
- `support_sbwc`
- `block_interval_cycle`

현재 예제 HW:
- `config/hw/byrp_v1.yaml`
- `config/hw/rgbp_v1.yaml`
- `config/hw/yuvp_v1.yaml`
- `config/hw/mcfp_v1.yaml`
- `config/hw/mcsc_v1.yaml`

## 4.2 Scenario YAML

scenario YAML은 런타임 workload를 정의합니다.

예:
- IP instance 이름
- OTF 포트 크기
- DMA base address
- image/stat/random DMA shape
- `timing_input_port`
- `timing_from_port`
- `start_condition`
- `links`

현재 예제 scenario:
- `config/scenario/isp_preview_4k_30fps.yaml`
- `config/scenario/isp_capture_4k.yaml`

## 4.3 Link 모델

현재 구현의 핵심은 `DMA -> DMA dependency list`가 아니라 `IP instance + endpoint graph`입니다.

### OTF 링크

- endpoint 형식: `IP.PORT`
- 예: `RGBP0.COUT0 -> YUVP0.CIN0`
- traffic을 직접 만들지는 않음
- IP 시작 시점을 제어하는 scheduling gate로 사용

### M2M 링크

- endpoint 형식: `IP.DMA`
- 예: `YUVP0.WDMA_NR -> MCFP0.RDMA_REF`
- producer DMA 완료 후 consumer RDMA가 시작
- 첫 consumer transaction에 dependency metadata가 들어갈 수 있음

## 4.4 Timing 선택 규칙

OTF 기반 IP는 scenario에서 사용하는 포트 크기를 명시합니다.

현재 timing 선택 우선순위:

1. DMA의 `timing_from_port`
2. IP의 `timing_input_port`
3. stat DMA의 경우, 위 둘이 없으면 같은 IP의 image read DMA fallback

`start_condition`은 시작 gate이고, `timing_input_port`는 timing 기준 포트를 뜻합니다. 둘은 역할이 다릅니다.

## 5. 핵심 데이터 구조

## 5.1 `MergedDMAConfig`

`MergedDMAConfig`는 runtime에서 사용하는 표준 DMA 설정 객체입니다.

핵심 필드:
- identity: `name`, `dma_name`, `instance_name`, `ip_name`, `ip_version`
- timing: `clock_mhz`, `start_ns`, `timing_from_port`, `timing_width`, `timing_height`, `timing_format`
- address: `base_dva`, `stride_byte`, `pattern`, `tile_width`, `tile_height`
- image/stat/random shape: `width`, `height`, `format`, `bitwidth`, `grid_width`, `grid_height`, `access_count`
- bus metadata: `bus_width_byte`, `max_outstanding`, `fifo_depth`, `xiu_port`, `hint`
- behavior: `direction`, `type`, `sbwc`, `comp_ratio`

특히 stat DMA용으로 아래 계산 property를 가집니다.

- `stat_block_count`
- `stat_cell_size_byte`

## 5.2 `Transaction`

`Transaction`은 최종 trace의 최소 단위입니다.

핵심 필드:
- `ts_ns`
- `txn_id`
- `port`
- `txn_type`
- `address`
- `size_byte`
- `burst`
- `hint`
- `sbwc`
- `dep`
- `delta_ns`

## 6. DMA 모델

## 6.1 BaseDMA

공통 책임:
- clock domain 연결
- direction -> `Read`/`Write` 변환
- 공통 transaction 생성
- burst 기본값 제공

## 6.2 ImageDMA

현재 image DMA는 다음을 처리합니다.

- format -> plane 해석
- raster / tile 패턴
- PPC 기반 beat/line timing
- SBWC header/payload 분리
- OTF input 기준 timing 적용

timing 계산은 `timing_width/timing_height/timing_format`가 있으면 그것을 우선 사용하고, 없으면 DMA 자신의 `width/height/format`을 사용합니다.

즉:
- 주소량은 실제 DMA output/read shape 기준
- timing 분포는 입력 기준 shape를 따를 수 있음

## 6.3 StatDMA

현재 stat DMA는 “수동 block 수열”이 아니라 “입력 grid 기반 stat sample 출력” 모델입니다.

scenario 예:

```yaml
- name: WDMA_STAT
  base_dva: 0x118000000
  width: 40
  height: 30
  format: STAT
  bitwidth: 16
  grid_width: 96
  grid_height: 72
  start_ns: 500
```

현재 의미:
- `width`, `height`: stat output 해상도
- `grid_width`, `grid_height`: 입력 도메인에서 한 stat sample이 담당하는 셀 크기(px)
- `format`, `bitwidth`: stat sample payload 크기 계산용
- `start_ns`: frame 시작 대비 offset

현재 구현 규칙:
- 입력 timing size는 `timing_from_port` 또는 IP timing source에서 가져옴
- `output width == ceil(input width / grid_width)`
- `output height == ceil(input height / grid_height)`
- sample당 byte = `stat_format_components(format) * bitwidth / 8`
- sample은 raster 순서로 생성
- sample 간 간격은 HW의 `block_interval_cycle`

예:
- 입력 `3840x2160`
- grid `96x72`
- output `40x30`
- `STAT/16bit`
- sample당 `2 byte`

이 경우 traffic은 `2 byte` request가 `1200ns` 간격으로 듬성듬성 생성됩니다.

## 6.4 RandomDMA

random DMA는 `interval_cycle` 간격으로 접근을 생성하고, 주소 분포는 `Random1DPattern` 또는 `Random2DPattern`가 담당합니다.

## 7. Scheduling 설계

## 7.1 IP 단위 순서

현재 simulator는 링크 graph를 기반으로 instance topological order를 구합니다.

즉 실행 순서는 DMA 나열 순서가 아니라 IP graph 구조에 의해 정해집니다.

## 7.2 OTF gate

OTF 링크는 producer instance 완료 시점 기준으로 consumer instance의 시작 가능 시점을 정합니다.

`start_condition.policy`:
- `all`: 모든 입력 준비 후 시작
- `any`: 하나라도 준비되면 시작

## 7.3 DMA 시작 시각

실제 DMA 시작 시각은 대략 아래 규칙입니다.

```text
actual_start_ns = max(frame_base_ns + start_ns, instance_ready_ns)
```

즉 `start_ns`는 절대 timestamp가 아니라 frame base 대비 local offset입니다.

## 7.4 M2M dependency

read DMA에 대해 `m2m` 링크가 있으면:
- source write DMA 완료 시점 이후에 시작
- 첫 consumer transaction에 dependency metadata 부여 가능
- 여러 M2M 입력이 있으면 가장 늦게 준비되는 source 기준

## 7.5 Frame duration

`duration_ns > 0`이면:
- frame end를 넘는 transaction은 잘립니다
- warning이 기록됩니다

`duration_ns == 0`이면:
- 해당 frame의 마지막 transaction 이후 다음 frame이 시작됩니다

## 8. Output 설계

## 8.1 `traffic.txt`

특징:
- line 기반 텍스트
- deterministic sort 후 저장
- header에 scenario/HW/profile metadata 포함
- comment 제거 옵션 지원

field:
- `ts`
- `id`
- `port`
- `type`
- `address`
- `bytes`
- `burst`
- `hint`
- `sbwc`
- `dep`
- `delta`

현재 `bytes`는 “transaction payload bytes”입니다.  
즉 stat DMA처럼 2-byte transaction도 허용됩니다.

## 8.2 `summary.txt`

사람이 검토하기 쉬운 텍스트 리포트입니다.

섹션:
- scenario metadata
- DMA summary
- XIU summary
- validation warnings/errors

## 8.3 `bw_plot.html`

현재 그래프 구성:
- DMA Bandwidth Over Time (Read+Write)
- DMA Bandwidth Over Time (Read)
- DMA Bandwidth Over Time (Write)
- XIU Port Aggregate Bandwidth (Read+Write)
- XIU Port Aggregate Bandwidth (Read)
- XIU Port Aggregate Bandwidth (Write)
- Average / Peak Bandwidth Table
- Transaction Density Heatmap

기본 window는 `10us`입니다.

중요한 점:
- 그래프는 raw transaction이 아니라 window 평균 BW입니다
- 그래서 stat DMA는 raw spike 대신 작은 평균 곡선처럼 보일 수 있습니다

## 9. Validation 설계

현재 `ConfigLoader._validate()`가 주요 교차 검증을 담당합니다.

예:
- HW 포트 / DMA 존재 여부
- OTF endpoint 방향 일치
- M2M source=write, target=read
- stride undersize / padding
- unsupported SBWC
- timing 포트 존재 여부
- stat output과 input-grid 관계 일치
- address overlap 경고

## 10. CLI 설계

현재 CLI는 `argparse` 기반입니다.

명령:
- `run`
- `validate`
- `summary`
- `filter`

기본 동작:
- `run`: config 로드 -> simulation -> `traffic.txt`/`summary.txt`/`bw_plot.html`
- `summary`: 기존 `traffic.txt` header metadata를 읽어 summary/graph 재생성
- `filter`: port/XIU/time 범위 기준 추출

## 11. 현재 구현과 초기 스펙의 차이

현재 코드는 실제 사용 가능 상태지만, 초기 목표 스택과는 차이가 있습니다.

- CLI는 `click`이 아니라 `argparse`
- schema는 `pydantic`이 아니라 dataclass 검증
- simulator는 `SimPy`가 아니라 custom scheduler
- summary는 `pandas` 없이도 동작
- YAML은 stdlib fallback 지원

이 차이는 실행 안정성을 위한 선택이며, strict spec alignment가 필요하면 별도 리팩터링이 필요합니다.

## 12. 남은 기술 부채

- `grid_width/grid_height` 이름은 현재 “grid cell 크기(px)” 의미라 혼동 여지가 있음
- stat format 체계는 아직 단순화되어 있음
- BW graph는 stat의 raw sparse 성격을 직접 보여주지는 않음
- SBWC 식은 논리 모델 수준이며 format별 golden tuning은 더 필요함
- end-to-end golden numeric regression은 충분하지 않음

## 13. 검증 상태

현재 작업 기준:
- 예제 scenario 2종 validate 통과
- `pytest` 통과
- `output/traffic.txt`, `output/summary.txt`, `output/bw_plot.html` 생성 가능

즉 문서 기준이 아니라 실제 코드 기준으로 현재 workflow는 정상 동작하는 상태입니다.
