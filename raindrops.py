import time
import random
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

# Set up RGB matrix options
options = RGBMatrixOptions()
options.hardware_mapping = 'regular'  # Change this if needed
options.rows = 48  # Number of rows on your RGB matrix
options.cols = 96  # Number of columns on your RGB matrix
options.chain_length = 1  # Number of boards daisy-chained
options.parallel = 1  # Number of parallel chains
options.row_address_type = 0  # Change this if needed
options.brightness = 100  # Adjust brightness as desired

matrix = RGBMatrix(options=options)

font = graphics.Font()
font.LoadFont("./fonts/9x18B.bdf")
textColor = graphics.Color(255, 255, 255)
textColor_shadow = graphics.Color(0, 0, 255)

# Define colors
color_white = (153, 255, 255)
color_black = (0, 0, 0)

# Define raindrop class
class Raindrop:
    def __init__(self):
        self.x = random.randint(0, options.cols - 1)
        self.y = 0
        self.speed = random.randint(1, 3)
    
    def fall(self):
        self.y += self.speed

# Create empty matrix
canvas = [[color_black for _ in range(options.cols)] for _ in range(options.rows)]

# List to hold raindrops
raindrops = []
loop_end = 0

try:
    while loop_end < 300:
        # Add new raindrops periodically
        if random.random() < 1:
            raindrops.append(Raindrop())
        
        # Clear the canvas
        canvas = [[color_black for _ in range(options.cols)] for _ in range(options.rows)]
        
        # Update and draw raindrops
        for raindrop in raindrops:
            if raindrop.y < options.rows:
                canvas[raindrop.y][raindrop.x] = color_white
                raindrop.fall()
            else:
                raindrops.remove(raindrop)
        
        # Show the canvas on the RGB matrix
        for y in range(options.rows):
            for x in range(options.cols):
                r, g, b = canvas[y][x]
                matrix.SetPixel(x, y, r, g, b)
            #graphics.DrawText(matrix, font, 29, 21, textColor_shadow, 'RAIN')
            #graphics.DrawText(matrix, font, 25, 33, textColor_shadow, 'DELAY')
            graphics.DrawText(matrix, font, 30, 22, textColor, 'RAIN')
            graphics.DrawText(matrix, font, 26, 34, textColor, 'DELAY')

        time.sleep(0.03)  # Adjust the delay to control animation speed
        loop_end += 1

except KeyboardInterrupt:
    matrix.Clear()