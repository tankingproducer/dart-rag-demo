"""DART XML 구조를 모사한 합성 샘플 (파이프라인 검증용). 수치는 실제 공시 기준 근사치.
실데이터 인제스트 시에는 사용하지 않음."""

_BIZ_2023 = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><BODY>
<SECTION-1><TITLE ATOC="Y">I. 회사의 개요</TITLE>
 <SECTION-2><TITLE>1. 회사의 개요</TITLE>
  <P>당사는 1969년 1월 13일 삼성전자공업주식회사로 설립되었으며, 1975년 6월 11일 한국거래소에 상장되었습니다.</P>
  <P>당사의 본점은 경기도 수원시 영통구 삼성로 129에 소재하고 있습니다.</P>
  <P>당사는 본사를 거점으로 한국과 DX 부문 산하 해외 9개 지역총괄 및 DS 부문 산하 해외 5개 지역총괄의 생산·판매법인, SDC, Harman 등 232개의 종속기업으로 구성된 글로벌 전자기업입니다.</P>
 </SECTION-2>
 <SECTION-2><TITLE>4. 주식의 총수 등</TITLE>
  <P>(단위 : 주)</P>
  <TABLE><THEAD><TR><TH>구 분</TH><TH>보통주</TH><TH>우선주</TH><TH>합계</TH></TR></THEAD>
  <TBODY><TR><TD>발행할 주식의 총수</TD><TD>20,000,000,000</TD><TD>5,000,000,000</TD><TD>25,000,000,000</TD></TR>
  <TR><TD>현재까지 발행한 주식의 총수</TD><TD>5,969,782,550</TD><TD>822,886,700</TD><TD>6,792,669,250</TD></TR>
  <TR><TD>발행주식의 총수</TD><TD>5,969,782,550</TD><TD>822,886,700</TD><TD>6,792,669,250</TD></TR></TBODY></TABLE>
 </SECTION-2>
</SECTION-1>
<SECTION-1><TITLE ATOC="Y">II. 사업의 내용</TITLE>
 <SECTION-2><TITLE>1. 사업의 개요</TITLE>
  <P>당사는 본사를 거점으로 DX 부문과 DS 부문 및 SDC, Harman 으로 구성되어 있습니다. DX 부문은 TV, 모니터, 냉장고, 세탁기, 에어컨, 스마트폰, 네트워크시스템, 컴퓨터 등을 생산·판매합니다.</P>
  <P>DS 부문은 DRAM, NAND Flash, 모바일AP 등의 반도체 제품을 생산·판매하고 있습니다. SDC 는 스마트폰용 OLED 패널 등을, Harman 은 디지털 콕핏, 카오디오 등을 생산·판매합니다.</P>
 </SECTION-2>
 <SECTION-2><TITLE>4. 매출 및 수주상황</TITLE>
  <P>당사의 2023년 부문별 매출은 다음과 같습니다. (단위 : 억원)</P>
  <TABLE><THEAD><TR><TH>부문</TH><TH>주요제품</TH><TH>제55기(2023년)</TH><TH>제54기(2022년)</TH></TR></THEAD>
  <TBODY><TR><TD>DX 부문</TD><TD>TV, 스마트폰, 생활가전 등</TD><TD>1,699,691</TD><TD>1,824,897</TD></TR>
  <TR><TD>DS 부문</TD><TD>DRAM, NAND, 모바일AP 등</TD><TD>665,945</TD><TD>984,553</TD></TR>
  <TR><TD>SDC</TD><TD>스마트폰용 OLED 패널 등</TD><TD>309,806</TD><TD>343,826</TD></TR>
  <TR><TD>Harman</TD><TD>디지털 콕핏, 카오디오 등</TD><TD>143,885</TD><TD>132,137</TD></TR>
  <TR><TD>합계</TD><TD></TD><TD>2,589,355</TD><TD>3,022,314</TD></TR></TBODY></TABLE>
 </SECTION-2>
 <SECTION-2><TITLE>6. 주요계약 및 연구개발활동</TITLE>
  <P>당사는 2023년 연구개발비로 28조 3,528억원을 지출하였으며, 이는 매출액 대비 10.9% 수준입니다. 2022년 연구개발비는 24조 9,192억원(매출 대비 8.2%)이었습니다.</P>
 </SECTION-2>
</SECTION-1>
<SECTION-1><TITLE ATOC="Y">III. 재무에 관한 사항</TITLE>
 <SECTION-2><TITLE>1. 요약재무정보</TITLE>
  <P>가. 요약연결재무정보 (단위 : 백만원)</P>
  <TABLE><THEAD><TR><TH>구 분</TH><TH>제55기(2023년)</TH><TH>제54기(2022년)</TH><TH>제53기(2021년)</TH></TR></THEAD>
  <TBODY><TR><TD>매출액</TD><TD>258,935,494</TD><TD>302,231,360</TD><TD>279,604,799</TD></TR>
  <TR><TD>영업이익</TD><TD>6,566,976</TD><TD>43,376,630</TD><TD>51,633,856</TD></TR>
  <TR><TD>당기순이익</TD><TD>15,487,100</TD><TD>55,654,077</TD><TD>39,907,450</TD></TR>
  <TR><TD>자산총계</TD><TD>455,905,980</TD><TD>448,424,507</TD><TD>426,621,158</TD></TR>
  <TR><TD>부채총계</TD><TD>92,228,115</TD><TD>93,674,903</TD><TD>121,721,227</TD></TR>
  <TR><TD>자본총계</TD><TD>363,677,865</TD><TD>354,749,604</TD><TD>304,899,931</TD></TR></TBODY></TABLE>
 </SECTION-2>
 <SECTION-2><TITLE>6. 배당에 관한 사항</TITLE>
  <P>당사는 2023년 연간 총 9조 8,094억원의 배당을 실시하였습니다. 보통주 1주당 배당금은 연간 1,444원(분기 361원 × 4)이며, 연결 현금배당성향은 63.3% 입니다.</P>
 </SECTION-2>
</SECTION-1>
<SECTION-1><TITLE ATOC="Y">VIII. 임원 및 직원 등에 관한 사항</TITLE>
 <SECTION-2><TITLE>2. 직원 등 현황</TITLE>
  <P>2023년 12월 31일 기준 당사의 직원 수는 124,804명이며, 1인 평균 급여액은 1억 2,000만원입니다. (단위 : 명, 백만원)</P>
  <TABLE><THEAD><TR><TH>사업부문</TH><TH>직원수</TH><TH>평균근속연수</TH><TH>연간급여총액</TH><TH>1인평균급여액</TH></TR></THEAD>
  <TBODY><TR><TD>DX</TD><TD>51,266</TD><TD>13.0</TD><TD>6,051,468</TD><TD>119</TD></TR>
  <TR><TD>DS</TD><TD>73,538</TD><TD>11.5</TD><TD>8,927,760</TD><TD>121</TD></TR></TBODY></TABLE>
 </SECTION-2>
</SECTION-1>
</BODY></DOCUMENT>"""

_Q3_2024 = """<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT><BODY>
<SECTION-1><TITLE ATOC="Y">II. 사업의 내용</TITLE>
 <SECTION-2><TITLE>4. 매출 및 수주상황</TITLE>
  <P>2024년 3분기 누적 부문별 매출은 다음과 같습니다. (단위 : 억원)</P>
  <TABLE><THEAD><TR><TH>부문</TH><TH>제56기 3분기 누적(2024년 1~9월)</TH><TH>제55기 3분기 누적(2023년 1~9월)</TH></TR></THEAD>
  <TBODY><TR><TD>DX 부문</TD><TD>1,306,584</TD><TD>1,278,806</TD></TR>
  <TR><TD>DS 부문</TD><TD>805,490</TD><TD>444,155</TD></TR>
  <TR><TD>SDC</TD><TD>212,594</TD><TD>218,873</TD></TR>
  <TR><TD>Harman</TD><TD>106,158</TD><TD>104,458</TD></TR>
  <TR><TD>합계</TD><TD>2,251,014</TD><TD>1,914,164</TD></TR></TBODY></TABLE>
 </SECTION-2>
</SECTION-1>
<SECTION-1><TITLE ATOC="Y">III. 재무에 관한 사항</TITLE>
 <SECTION-2><TITLE>1. 요약재무정보</TITLE>
  <P>요약연결재무정보 (단위 : 백만원)</P>
  <TABLE><THEAD><TR><TH>구 분</TH><TH>제56기 3분기(2024.09)</TH><TH>제55기(2023.12)</TH></TR></THEAD>
  <TBODY><TR><TD>매출액(누적)</TD><TD>225,101,364</TD><TD>258,935,494</TD></TR>
  <TR><TD>영업이익(누적)</TD><TD>26,839,612</TD><TD>6,566,976</TD></TR>
  <TR><TD>자산총계</TD><TD>487,201,839</TD><TD>455,905,980</TD></TR></TBODY></TABLE>
  <P>2024년 3분기(7~9월) 당분기 매출액은 79조 987억원, 영업이익은 9조 1,834억원입니다.</P>
 </SECTION-2>
</SECTION-1>
</BODY></DOCUMENT>"""

SAMPLES = [
    ({"corp_name": "삼성전자", "report_type": "사업보고서", "period": "2023.12", "rcept_no": "SAMPLE-A001-2023",
      "rcept_dt": "20240312", "report_nm": "사업보고서 (2023.12)"}, _BIZ_2023),
    ({"corp_name": "삼성전자", "report_type": "분기보고서", "period": "2024.09", "rcept_no": "SAMPLE-A003-2024Q3",
      "rcept_dt": "20241114", "report_nm": "분기보고서 (2024.09)"}, _Q3_2024),
]
