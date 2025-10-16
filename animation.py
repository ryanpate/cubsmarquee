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

# Load image
x = 1
cubs_image_path = "./logos/cubs.png"
cubs_image = Image.open(cubs_image_path)
cubs_image_inv = cubs_image.transpose(Image.FLIP_LEFT_RIGHT)
cubs_image_inv.save('./logos/cubs_inv.png')
cubs_image_inv_path = "./logos/cubs_inv.png"
win_image_path = './logos/Cubs_W_Flag.png'
win_image = Image.open(win_image_path)

while True:
    for a in range(28, 0, -2):
        cubs_image = Image.open(cubs_image_path)
        canvas.Clear()
        cubs_image_pos = (x, 0)
        cubs_image_newsize = (a, 28)
        cubs_image = cubs_image.resize(cubs_image_newsize)
        canvas.SetImage(cubs_image.convert("RGB"), x, 0)
        canvas = matrix.SwapOnVSync(canvas)
        x += 1
        time.sleep(.02)
    for c in range(1, 28, 2):
        cubs_image_inv = Image.open(cubs_image_inv_path)
        canvas.Clear()
        cubs_image_pos = (x, 0)
        cubs_image_inv_newsize = (c, 28)
        cubs_image_inv = cubs_image_inv.resize(cubs_image_inv_newsize)
        canvas.SetImage(cubs_image_inv.convert("RGB"), x, 0)
        canvas = matrix.SwapOnVSync(canvas)
        x -= 1
        time.sleep(.02)
    for d in range(28, 0, -2):
        cubs_image_inv = Image.open(cubs_image_inv_path)
        canvas.Clear()
        cubs_image_pos = (x, 0)
        cubs_image_inv_newsize = (d, 28)
        cubs_image_inv = cubs_image_inv.resize(cubs_image_inv_newsize)
        canvas.SetImage(cubs_image_inv.convert("RGB"), x, 0)
        canvas = matrix.SwapOnVSync(canvas)
        x += 1
        time.sleep(.02)
    for b in range(1, 28, 2):
        cubs_image = Image.open(cubs_image_path)
        canvas.Clear()
        cubs_image_pos = (x, 0)
        cubs_image_newsize = (b, 28)
        cubs_image = cubs_image.resize(cubs_image_newsize)
        canvas.SetImage(cubs_image.convert("RGB"), x, 0)
        canvas = matrix.SwapOnVSync(canvas)
        x -= 1
        time.sleep(.02)
    canvas.Clear()
    canvas.SetImage(win_image.convert('RGB'), 1, 5)
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(2)

