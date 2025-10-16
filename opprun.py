from PIL import Image, ImageDraw
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
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

# Load BDF font
font = graphics.Font()
font.LoadFont("./fonts/7x13B.bdf")

# Load image
image_path = "./marquee.png"
image = Image.open(image_path)


opp_image_path = './logos/STL.png'
opp_image = Image.open(opp_image_path)
opp_image_left_path = './logos/STL.png'
opp_image_left = Image.open(opp_image_path)

for x in range(-24,220,2):
    canvas.Clear()
    opp_image_pos = (x, 12)
    opp_image_newsize = (opp_image.size[0], 28)
    opp_image = opp_image.resize(opp_image_newsize)
    output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
    output_image.paste(opp_image, opp_image_pos)
    opp_image_pos_left = (x-119, 12)
    opp_image_newsize_left = (opp_image_left.size[0], 28)
    opp_image_left = opp_image_left.resize(opp_image_newsize)
    output_image_left = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
    output_image.paste(opp_image_left, opp_image_pos_left)
    canvas.SetImage(output_image.convert("RGB"), 0, 0)
    scored_font = graphics.Font()
    scored_font.LoadFont('./fonts/9x18B.bdf')
    scored_color = graphics.Color(255, 0, 0)
    scored_shadow_color = graphics.Color(255, 255, 255)
    graphics.DrawText(canvas, scored_font, x-90, 30, scored_shadow_color, 'RUN SCORED')
    graphics.DrawText(canvas, scored_font, x-91, 29, scored_color, 'RUN SCORED')

    canvas = matrix.SwapOnVSync(canvas)
