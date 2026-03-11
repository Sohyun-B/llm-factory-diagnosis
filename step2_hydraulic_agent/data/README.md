# 데이터 다운로드 안내

UCI Hydraulic System Condition Monitoring 데이터셋을 이 폴더에 넣어주세요.

## 다운로드
- Kaggle: https://www.kaggle.com/datasets/jjacostupa/condition-monitoring-of-hydraulic-systems
- UCI: https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems

## 필요한 파일 목록
압력 (100Hz): PS1.txt PS2.txt PS3.txt PS4.txt PS5.txt PS6.txt
전력 (100Hz): EPS1.txt
유량 (10Hz):  FS1.txt FS2.txt
온도 (1Hz):   TS1.txt TS2.txt TS3.txt TS4.txt
진동 (1Hz):   VS1.txt
냉각 (1Hz):   CE.txt CP.txt SE.txt
레이블:       profile.txt

## profile.txt 컬럼 순서
1. 냉각기 (Cooler): 3=고장임박 / 20=성능저하 / 100=정상
2. 밸브 (Valve): 73=고장임박 / 80=심각지연 / 90=경미지연 / 100=최적
3. 내부 펌프 누수 (Pump): 0=없음 / 1=약함 / 2=심각
4. 어큐뮬레이터 (Accumulator): 90=고장임박 / 100=심각저하 / 115=약간저하 / 130=최적
5. 안정 플래그 (Stable): 0=불안정 / 1=안정
