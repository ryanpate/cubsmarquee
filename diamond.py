from PIL import Image, ImageDraw
import PIL

# Set the dimensions of the matrix
width = 5
height = 5

# Create a new RGB image with white background
image = Image.new("RGB", (width, height))
draw = ImageDraw.Draw(image)

# Calculate the center of the matrix
center_x = width // 2
center_y = height // 2

# Calculate the length of each side of the diamond
side_length = min(center_x, center_y)

# Draw the diamond
draw.polygon([(center_x, center_y - side_length),  # Top point
              (center_x + side_length, center_y),  # Right point
              (center_x, center_y + side_length),  # Bottom point
              (center_x - side_length, center_y)],  # Left point
             fill="#FFE900")

# Save the image
image.save("base.png")

im1 = Image.open('./base.png')
im1 = im1.rotate(45, expand = 1)

im1.save("base.png")
