from PIL import Image, ImageDraw
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
import os, time

path = './/logos'
dir_list = os.listdir(path)

matrix_options = RGBMatrixOptions()
matrix_options.rows = 48
matrix_options.cols = 96
matrix_options.chain_length = 1
matrix_options.parallel = 1
matrix_options.hardware_mapping = 'regular'  # Check your specific mapping

opp_image = Image.open(opp_image_path)
opp_image_newsize = (opp_image.size[0], 30)
opp_image = opp_image.resize(opp_image_newsize)
opp_image_height = opp_image.size[1]
cubs_image_path = './logos/cubs.png'
cubs_image = Image.open(cubs_image_path)
cubs_image_pos = (3, 0)
opp_image_pos = (64, 0)

output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))

for x in dir_list:
    opp_image_path = './logos/' + x
print(opp_image_height)
matrix = RGBMatrix(options=matrix_options)
canvas = matrix.CreateFrameCanvas()
canvas.SetImage(output_image.convert("RGB"), 0, 0)
output_image.paste(cubs_image, cubs_image_pos)
output_image.paste(opp_image, opp_image_pos)


while True:
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(10)
    canvas.Clear()
