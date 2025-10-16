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

output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))

# Load image
x = 1
cubs_image_path = "./logos/cubs.png"
cubs_image = Image.open(cubs_image_path)
while True:
    for i in range(28, 0, -2):
        canvas.Clear()
        cubs_image_pos = (x, 0)
        cubs_image_newsize = (i, 28)
        cubs_image = cubs_image.resize(cubs_image_newsize)
        output_image.paste(cubs_image, cubs_image_pos)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        canvas = matrix.SwapOnVSync(canvas)
        x += 1
        time.sleep(1)
    for j in range(1, 28, 2):
        canvas.Clear()
        cubs_image_pos = (x, 0)
        cubs_image_newsize = (j, 28)
        cubs_image = cubs_image.resize(cubs_image_newsize)
        output_image.paste(cubs_image, cubs_image_pos)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        canvas = matrix.SwapOnVSync(canvas)
        x -= 1
        time.sleep(1)
