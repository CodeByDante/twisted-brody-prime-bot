
import os

target = os.path.join("cookies", "cookies_pornhub.txt")
content = """# Netscape HTTP Cookie File
# https://curl.haxx.se/rfc/cookie_spec.html
# This is a generated file! Do not edit.

.pornhub.com	TRUE	/	TRUE	1796666933	ss	622127382887760542
.pornhub.com	TRUE	/	TRUE	1796666933	sessid	813993118168190581
.pornhub.com	TRUE	/	TRUE	1767722933	comp_detect-cookies	64018.100000
.pornhub.com	TRUE	/	TRUE	1767722933	fg_afaf12e314c5419a855ddc0bf120670f	83835.100000
.pornhub.com	TRUE	/	TRUE	1767722933	fg_439f2555043a44b8bd91161b5deddd29	89015.100000
.pornhub.com	TRUE	/	TRUE	1796687859	__l	6935C2B4-42FE722901BB2FEA3F-3DE8E374
.pornhub.com	TRUE	/	FALSE	1800802471	_ga	GA1.1.782546871.1765130937
.pornhub.com	TRUE	/	TRUE	1796666949	lvv	250286288644564106
.pornhub.com	TRUE	/	TRUE	1796666949	vlc	479930477885370351
.pornhub.com	TRUE	/	TRUE	1796917498	cookieConsent	3
.pornhub.com	TRUE	/	FALSE	1780933497	g_state	{"i_l":0,"i_ll":1765381478170}
.pornhub.com	TRUE	/	TRUE	1781192698	il	v1ZoCJCTxtZJoUuds-tYF1eIoveDUJD-q2he-Q9CwFncMxNzgxMTkyNjk4SkZ3NGhMdzZOMk40RXFUR2RvV0M1WHNmUTI2dS0zanFyZDR2TFNDaQ..
.pornhub.com	TRUE	/	TRUE	1796917498	bs	82ec02b270e1a83342e7c7fcd2f53cc7
.pornhub.com	TRUE	/	TRUE	1796917498	bsdd	82ec02b270e1a83342e7c7fcd2f53cc7
.pornhub.com	TRUE	/	TRUE	1767977580	fg_7d31324eedb583147b6dcbea0051c868	66137.100000
es.pornhub.com	FALSE	/	FALSE	1766242809	etavt	%7B%22664773de8baed%22%3A%224_3_2_pornhub.SearchVideoService.194.195%7C8%22%2C%22684455c4cb7ee%22%3A%224_3_2_pornhub.SearchVideoService.194.195%7C7%22%2C%2269103d863cd97%22%3A%224_3_2_pornhub.SearchVideoService.194.195%7C6%22%2C%2268c9b7019ccda%22%3A%225_2_2_pornhub.video_recommendation.141%7C5%22%2C%2268c42d3234640%22%3A%225_2_2_pornhub.video_recommendation.141%7C4%22%2C%22688ad2e03e82e%22%3A%221_24_2_NA%7C3%22%2C%2267bdef8c27df6%22%3A%221_24_2_NA%7C2%22%2C%226857529489ecf%22%3A%221_24_2_NA%7C1%22%2C%2264b842704b9af%22%3A%224_3_2_pornhub.SearchVideoService.208.209%7C0%22%7D
.pornhub.com	TRUE	/	TRUE	1766328870	ua	89db729cfcdc129111f017b0e7ac324a
.pornhub.com	TRUE	/	TRUE	1766847270	platform	pc
.pornhub.com	TRUE	/	TRUE	1768834470	fg_55e3b6f0afd46366d6fa797544b15af2	53123.100000
.pornhub.com	TRUE	/	TRUE	0	__s	6946B8A5-42FE722901BB232936-960B39B
.pornhub.com	TRUE	/	FALSE	1800802471	_ga_B39RFFWGYY	GS2.1.s1766242471$o9$g0$t1766242471$j60$l0$h0
.pornhub.com	TRUE	/	FALSE	1766246071	accessAgeDisclaimerPH	2
"""

with open(target, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated cookies_pornhub.txt")
