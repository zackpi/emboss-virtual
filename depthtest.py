import cv2
import argparse
import numpy as np
from scipy.signal import find_peaks

# parse the arguments from the commandline
parser = argparse.ArgumentParser()
parser.add_argument("filename", type=str, help="the image file to convert")
args = parser.parse_args()

# read in the image and convert to HSV to extract value channel
img = cv2.imread(args.filename)
horiz = cv2.flip(img, 1)  # pressing through the pattern flips the image horizontally
large = cv2.resize(horiz, (0,0), fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
h, v, s =  cv2.split(hsv)
blur = cv2.GaussianBlur(v, (3,3), 0)
edge = cv2.Canny(blur, 0, 50) # perform edge detection with a low slope threshold to capture all edges
kernel = np.ones((3,3),np.uint8)
mask = cv2.dilate(edge, kernel, iterations=1)
filt = cv2.bitwise_and(cv2.bitwise_not(mask), v) # filter the noisy edges out by masking off those regions

# get counts of times each value occurs in the filtered parts of the image
G = 3
N = 256 // G + 1
val_count = [0]*N
rows, cols = filt.shape
for i in range(rows):
  for j in range(cols):
    val_count[filt[i,j] // G] += 1
val_count[0] = 0

# detect peaks in the histogram, indicating discrete layers
val_log = np.array([0 if not vc else np.log(vc) for vc in val_count])
val_norm = [0]*N
k = 2*G
for i in range(N):  # use a windowed z-score to find prominent local maxima
  lo = max(0, i-k)
  hi = min(N, i+k)
  window = val_log[lo:hi]
  val_norm[i] = (val_log[i] - np.mean(window)) / np.std(window)
val_norm = np.array(val_norm)
colors, _ = find_peaks(val_norm, height=1, distance=15//G)

# separate into layers by color and apply an edge gradient
# black -> clear to imitate shadows in regions of neg vertical slope
# white -> clear to imitate highlights in regions of pos vert slope
result = np.full_like(v, 128)
upper = np.zeros_like(v)
for i in range(len(colors)-1, 0, -1):
  lowc = np.array([0, G*colors[i]-15, 0])
  highc = np.array([255, G*colors[i]+15, 255])
  layer = cv2.inRange(hsv, lowc, highc)
  
  # don't allow lower layers to overlap upper layers
  composite = cv2.bitwise_or(layer, upper)
  composite = cv2.morphologyEx(composite, cv2.MORPH_CLOSE, kernel)
  upper = composite

  # find the gradient in the y direction
  # ypos is positive dY and represents highlights
  # yneg is negative dY and represents shadows
  sobel_ypos = cv2.Sobel(composite, cv2.CV_8U, 0, 1, ksize=1)
  sobel_yneg = cv2.Sobel(cv2.bitwise_not(composite), cv2.CV_8U, 0, 1, ksize=1)

  # iteratively add shadows that get lighter and lighter as they shift up
  # and add highlights that get darker and darker as thy shift down
  S = 5
  highlight = np.uint8(sobel_ypos)
  shadow = np.uint8(sobel_yneg)
  for j in range(1, S):
    txlate_down = np.float32([[1,0,0],[0,1,j]])
    txlate_up = np.float32([[1,0,0],[0,1,-j]])
    hlj = np.uint8(cv2.warpAffine(sobel_ypos, txlate_down, (cols,rows)) / (2**j))
    sdj = np.uint8(cv2.warpAffine(sobel_yneg, txlate_up, (cols,rows)) / (2**j))
    highlight = hlj + cv2.bitwise_and(cv2.bitwise_not(hlj), highlight)
    shadow = sdj + cv2.bitwise_and(cv2.bitwise_not(sdj), shadow)
 
  mask = cv2.bitwise_not(cv2.threshold(cv2.bitwise_not(result), 128, 256, cv2.THRESH_BINARY)[1])
  mask = cv2.bitwise_and(mask, cv2.bitwise_not(cv2.threshold(result, 128, 256, cv2.THRESH_BINARY)[1]))
  result += cv2.bitwise_and(highlight, highlight, mask=mask)//2
  result -= cv2.bitwise_and(shadow, shadow, mask=mask)//2

# set the hue and saturation to look like paper
# then construct a colored version and display it
h = np.full_like(v, 20)
s = np.full_like(v, 40)
v = cv2.add(result, 100)
hsv = cv2.merge((h,s,v))
bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
cv2.namedWindow("output", cv2.WINDOW_AUTOSIZE)
cv2.imshow("output", cv2.resize(bgr, (0,0), fx=.5, fy=.5, interpolation=cv2.INTER_LANCZOS4))

# handle exiting out of the window via the ESC / ENTER key or the X in the corner of the window
while cv2.getWindowProperty("output", cv2.WND_PROP_VISIBLE):
  k = cv2.waitKey(30) & 0xFF
  if k == 27 or k == 13:  # wait for ESC / ENTER key to exit
    cv2.destroyAllWindows()
  if k == ord('s'):  # wait for 's' key to save and exit
    cv2.imwrite("output.png", bgr)
    cv2.destroyAllWindows()
