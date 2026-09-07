# 将自定义提示音（仅 .wav）放在此目录。
# 程序启动会扫描全部 *.wav，在「杂项」页下拉框中选择。
#
# 默认回退：notify.wav
#
# 已内置示例（可直接在下拉框选择）：
#   qq_cough.wav 		— QQ 风格「咳咳」致敬合成音
#   soft_chime.wav              — 柔和双音风铃
#   gentle_ping.wav             — 清脆短 ping
#   crystal_bell.wav            — 水晶铃
#   soft_marimba.wav            — 轻木琴两音
#   bubble_pop.wav              — 气泡爆破
#   wood_knock.wav              — 轻敲门
#   ding.wav / notify.wav / windows_notify.wav — Windows 系统风格
#   QQ咳嗽 / QQ提示音 / QQ好友上线.wav — QQ原生铃声
#
# 新增音效：丢入本目录后重启软件即可识别，无需改代码。
# 重新生成合成音：python assets/sound/_gen_notify_wavs.py
