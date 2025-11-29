# globals.py
from vars import OWNER, CREDIT

processing_request = False
cancel_requested = False
caption = '/cc1'
endfilename = '/d'
thumb = '/d'
CR = f"{CREDIT}"
cwtoken = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...'
cptoken = "cptoken"
pwtoken = "pwtoken"

# watermark controls
# If vidwatermark == "/d" -> disabled. Otherwise watermark text (e.g. "Pglinsan")
vidwatermark = '/d'

# movement: "none" | "lr" (left->right) | "tb" (top->bottom)
watermark_movement = "none"

# watermark speed (units for ffmpeg expression; higher = faster). Default 100
watermark_speed = 100

# whether to use center or corner when stationary
watermark_position = "center"  # "center" or "bottom-right" (used when movement == none)

# CRF (video compression) default: 18 (near-lossless)
crf_value = 23

raw_text2 = '480'
quality = '480p'
res = '854x480'
topic = '/d'
