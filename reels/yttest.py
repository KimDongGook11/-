"""유튜브 업로드 진단: 6초짜리 시험 영상을 '일부 공개(unlisted)'로 올려
비공개로 잠기는지 확인하고 지웁니다."""
import subprocess
import tempfile
import time
import os

from . import youtube


def main():
    tok = youtube._token()
    ch = youtube.channel(tok)
    print("채널:", ch)
    if "경제" not in (ch or "") and os.environ.get("YT_TEST_ANY") != "true":
        print("❌ 경제원픽 채널이 아니라서 시험 업로드를 하지 않았어요. 토큰을 다시 받아 주세요.")
        return
    d = tempfile.mkdtemp()
    v, th = os.path.join(d, "t.mp4"), os.path.join(d, "t.jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x0A1020:s=1280x720:d=6",
                    "-f", "lavfi", "-i", "sine=f=440:d=6", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", v], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", v, "-frames:v", "1", th], check=True)
    vid, st = youtube.upload(v, "업로드 시험 (곧 삭제)", "자동 업로드 시험", privacy="unlisted", thumb=th)
    print("업로드:", vid, "요청 직후 상태:", st)
    info = {}
    for _ in range(12):
        time.sleep(15)
        info = youtube.status(vid, tok)
        s = info.get("status", {})
        print("  상태:", s.get("uploadStatus"), s.get("privacyStatus"), s.get("rejectionReason") or s.get("failureReason") or "")
        if s.get("uploadStatus") in ("processed", "rejected", "failed"):
            break
    priv = info.get("status", {}).get("privacyStatus")
    print("\n===== 결과 =====")
    if priv == "unlisted":
        print("✅ 잠기지 않음: 요청한 공개 상태(unlisted)가 유지됐어요 → 자동 공개 게시 가능")
    else:
        print(f"❌ 요청은 unlisted였는데 실제 상태는 {priv} → 비공개 잠금(감사 필요) 가능성")
    if os.environ.get("YT_TEST_KEEP") != "true":
        print("시험 영상 삭제:", youtube.delete(vid, tok))


if __name__ == "__main__":
    main()
