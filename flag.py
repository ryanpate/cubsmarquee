from PIL import Image, ImageDraw
from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions, graphics
from datetime import datetime
import statsapi, time

# Configuration
matrix_options = RGBMatrixOptions()
matrix_options.rows = 48
matrix_options.cols = 96
matrix_options.chain_length = 1
matrix_options.parallel = 1
matrix_options.hardware_mapping = 'regular'  # Check your specific mapping

# Initialize matrix
matrix = RGBMatrix(options=matrix_options)
canvas = matrix.CreateFrameCanvas()

for a in range(48, 4, -1):
    #draw flag pole
    canvas.SetPixel(19, a + 1, 153, 153, 0)
    canvas.SetPixel(22, a + 1, 153, 153, 0)
    canvas.SetPixel(19, a + 2, 153, 153, 0)
    canvas.SetPixel(22, a + 2, 153, 153, 0)
    canvas.SetPixel(20, a, 153, 153, 0)
    canvas.SetPixel(21, a, 153, 153, 0)
    canvas.SetPixel(19, a + 3, 0, 0, 0)
    canvas.SetPixel(22, a + 3, 0, 0, 0)
    canvas.SetPixel(19, a + 4, 0, 0, 0)
    canvas.SetPixel(22, a +  4, 0, 0, 0)
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(0.05)

#draw flag
for b in range(53):
    canvas.SetPixel(22 + b, 8, 255, 255, 255)
    for c in range(32):
        canvas.SetPixel(22 + b, 8 + c, 255, 255, 255)
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(0.05)

#draw W
win_image_path = './logos/Cubs_W_Flag.png'
win_image = Image.open(win_image_path)
canvas.SetImage(win_image.convert("RGB"), 24, 9)
canvas = matrix.SwapOnVSync(canvas)

while True:
    True