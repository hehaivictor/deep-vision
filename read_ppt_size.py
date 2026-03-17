import pptx
import sys

def read_presentation(file_path):
    prs = pptx.Presentation(file_path)
    width = prs.slide_width / 914400.0
    height = prs.slide_height / 914400.0
    print(f"Slide Size: {width} x {height} inches")

if __name__ == "__main__":
    read_presentation(sys.argv[1])
