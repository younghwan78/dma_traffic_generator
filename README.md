# DMA Traffic Generator

모바일 SoC 멀티미디어 IP의 DMA traffic을 생성하는 Python 기반 CLI 도구입니다.  
현재 구현은 ISP 계열 예제 시나리오를 기준으로 `OTF`, `M2M`, `SBWC`, `stat`, `random` DMA를 함께 다룹니다.
또한 MTNR용 피라미드 기반 `mtnr` DMA 모델과 M2M 예제 scenario를 포함합니다.

## 개요

입력:
- `config/hw/*.yaml`: IP 모델별 HW 고정 정보
- `config/scenario/*.yaml`: 인스턴스 연결, 포트 크기, DMA 런타임 설정

출력:
- `traffic.txt`: downstream 시뮬레이터 입력용 transaction trace
- `summary.txt`: 사람이 읽기 쉬운 요약 리포트
- `bw_plot.html`: Plotly 기반 BW 시각화

시간 단위는 전체적으로 `ns`를 사용합니다.

## 빠른 시작

```bash
python -m dma_traffic_gen run config/scenario/isp_preview_4k_30fps.yaml --hw-dir config/hw -o output
```

기본 그래프 window는 `10us`입니다. 더 완만한 평균 BW를 보고 싶으면 `--window-us 100`처럼 지정하면 됩니다.

## 주요 명령

- `run`: traffic 생성, summary 생성, graph 생성
  - `--split-by-dma` 옵션 사용 시 DMA 포트별로 개별 `traffic_*.txt` 파일을 분리 생성
- `validate`: YAML 로드/merge/교차 검증만 수행
- `summary`: 기존 `traffic.txt`로부터 `summary.txt`, `bw_plot.html` 재생성
- `filter`: 포트/XIU/시간 범위 기준으로 trace 일부 추출

예시:

```bash
python -m dma_traffic_gen validate config/scenario/isp_preview_4k_30fps.yaml --hw-dir config/hw
python -m dma_traffic_gen run config/scenario/isp_preview_4k_30fps.yaml --hw-dir config/hw -o output --window-us 10 --split-by-dma
python -m dma_traffic_gen summary output/traffic.txt -o output --window-us 100
python -m dma_traffic_gen filter output/traffic.txt --port BYRP0.WDMA_STAT --ts-from 0 --ts-to 2000000 -o filtered.txt
```

## 시나리오 모델

현재 시나리오 모델의 핵심은 `IP instance + endpoint graph`입니다.

- OTF 링크는 `IP.PORT -> IP.PORT`
- M2M 링크는 `IP.DMA -> IP.DMA`
- endpoint 이름은 fully-qualified name을 사용
  - 예: `RGBP0.COUT0`, `MCFP0.CIN0`, `YUVP0.WDMA_NR`, `MCFP0.RDMA_REF`

예시:

```yaml
links:
  - from: RGBP0.COUT0
    to: YUVP0.CIN0
    type: otf

  - from: YUVP0.WDMA_NR
    to: MCFP0.RDMA_REF
    type: m2m
    delta_ns: 0
```

## OTF 포트와 timing

OTF를 사용하는 IP는 scenario에서 사용하는 `CIN/COUT`의 크기와 포맷을 직접 적습니다.

```yaml
- name: MCSC0
  hw: mcsc_v1.yaml
  timing_input_port: CIN0
  ports:
    - name: CIN0
      width: 3840
      height: 2160
      format: YUV420_8BIT
```

규칙:
- `timing_input_port`: IP 기본 timing 기준 입력 포트
- `timing_from_port`: 특정 DMA가 IP 기본값 대신 따를 입력 포트 override
- `start_condition`: 해당 IP가 언제 시작 가능한지 결정하는 gate

`timing_from_port`는 현재 image/stat DMA에서 사용할 수 있습니다.

## Stat DMA 모델

현재 stat DMA는 예전의 수동 `block_count` 중심 모델이 아니라, 입력 기준 grid-cell output 모델입니다.

scenario에서 stat DMA는 보통 아래 필드를 가집니다.

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

의미:
- `width`, `height`: stat output 해상도
- `format`: stat sample 형식
- `bitwidth`: sample bit 수
- `grid_width`, `grid_height`: 입력 도메인에서 한 stat sample이 담당하는 셀 크기(px)
- `start_ns`: frame base 대비 DMA 시작 오프셋

현재 구현에서:
- sample당 payload byte는 `format + bitwidth`로 계산
- transaction 간격은 HW의 `block_interval_cycle`을 사용
- 입력 timing size는 `timing_from_port` 또는 `timing_input_port`를 통해 결정
- `output width/height == ceil(input width/height / grid size)`를 검증

예를 들어 입력이 `3840x2160`, grid가 `96x72`이면 output은 `40x30`이 됩니다.

## 그래프

`bw_plot.html`에는 다음이 포함됩니다.

- `DMA Bandwidth Over Time (Read+Write)`
- `DMA Bandwidth Over Time (Read)`
- `DMA Bandwidth Over Time (Write)`
- `XIU Port Aggregate Bandwidth (Read+Write)`
- `XIU Port Aggregate Bandwidth (Read)`
- `XIU Port Aggregate Bandwidth (Write)`
- `Average / Peak Bandwidth Table`
- `Transaction Density Heatmap`

주의:
- BW graph는 raw transaction이 아니라 time window 평균 BW입니다.
- stat DMA처럼 payload가 매우 작고 간격이 긴 경우, 완전한 spike가 아니라 작은 평균값 곡선으로 보일 수 있습니다.

## 현재 구현 기준 예제 파일

HW 예제:
- `config/hw/byrp_v1.yaml`
- `config/hw/rgbp_v1.yaml`
- `config/hw/yuvp_v1.yaml`
- `config/hw/mcfp_v1.yaml`
- `config/hw/mcsc_v1.yaml`
- `config/hw/mtnr_v1.yaml`

시나리오 예제:
- `config/scenario/isp_preview_4k_30fps.yaml`
- `config/scenario/isp_capture_4k.yaml`
- `config/scenario/isp_capture_4k_mtnr.yaml`

## 구현 메모

현재 코드는 실행 가능성과 이식성을 우선합니다.

- CLI는 `argparse` 기반
- schema는 dataclass 기반 검증
- YAML은 stdlib fallback 지원
- simulator는 SimPy 기반이 아닌 custom scheduling
- summary는 pandas 없이도 동작

즉 `pyproject.toml`에 선언된 목표 스택과 100% 동일한 구현은 아니지만, 실제 기능은 현재 코드 기준으로 동작합니다.
