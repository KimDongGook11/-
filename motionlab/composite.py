"""시험: 기존 원픽 영상(A안 레이아웃) 앞 25초의 가운데 카드 자리에 모션 그래픽을 덮어씌움.
제목·자막·음성·아웃트로 등 나머지는 기존 그대로."""
import subprocess
import sys

from PIL import Image, ImageDraw

src, motion, out = sys.argv[1], sys.argv[2], sys.argv[3]
X, Y, W, H, START, END = 80, 600, 920, 860, 1.3, 25.2
mask = Image.new("L", (W, H), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=36, fill=255)
mask.save("mask.png")
fc = (f"[1:v]setpts=PTS+{START}/TB,format=rgba[m];[2:v]format=gray[k];[m][k]alphamerge[mk];"
      f"[0:v][mk]overlay={X}:{Y}:enable='between(t,{START},{END - 0.05})':eof_action=pass[v]")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-t", str(END), "-i", src, "-i", motion, "-loop", "1", "-i", "mask.png",
                "-filter_complex", fc, "-map", "[v]", "-map", "0:a", "-t", str(END),
                "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "veryfast",
                "-c:a", "aac", "-b:a", "160k", out], check=True)
print("완료:", out)
