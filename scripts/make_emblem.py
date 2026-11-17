"""엠블럼 원본(흰 배경+그림자) → 검은 배경용 투명 PNG/WebP, 파비콘.

흰색 판정만으로는 금속 하이라이트(거의 흰색)까지 지워지므로,
'가장자리에서 이어진 큰 연결 영역'만 배경으로 본다(바깥 + 구멍 2개). 하이라이트는 몸통 안에 갇힌 작은 조각이라 남는다.
사용: python scripts/make_emblem.py <원본.png>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

APP = Path(__file__).resolve().parents[1] / "app"


def cut_background(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    near_white = (np.minimum(np.minimum(r, g), b) >= 214) & ((np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)) <= 12)
    lab, n = ndi.label(near_white)
    sizes = ndi.sum(near_white, lab, range(1, n + 1))
    big = {i + 1 for i, s in enumerate(sizes) if s > 4000}      # 바깥 배경 + 구멍
    bg = np.isin(lab, list(big))
    # 그림자: 배경에 닿아 있고, 무채색이며, 배경에서 30px 이내인 옅은 회색만 추가로 배경 취급(몸통 금속은 채도가 있거나 멀다)
    chroma = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
    shadow_like = (np.minimum(np.minimum(r, g), b) >= 150) & (chroma <= 14)
    bg = ndi.binary_dilation(bg, iterations=30, mask=shadow_like | bg)
    bg = ndi.binary_dilation(bg, iterations=1)                    # 흰 테두리 후광 제거를 위해 1px 먹어 들어감
    alpha = 1.0 - ndi.gaussian_filter(bg.astype(float), 0.9)      # 부드러운 가장자리
    return np.clip(alpha * 1.15 - 0.08, 0, 1)


def main(src: str) -> None:
    im = Image.open(src).convert("RGB")
    rgb = np.array(im)
    alpha = cut_background(rgb)
    rgba = np.dstack([rgb, (alpha * 255).astype(np.uint8)])
    out = Image.fromarray(rgba, "RGBA")
    out = out.crop(out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox())
    side = max(out.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(out, ((side - out.width) // 2, (side - out.height) // 2))
    sq.resize((560, 560), Image.LANCZOS).save(APP / "emblem.webp", quality=90, method=6)
    sq.resize((64, 64), Image.LANCZOS).save(APP / "favicon.png")
    print("emblem.webp", (APP / "emblem.webp").stat().st_size, "bytes")


if __name__ == "__main__":
    main(sys.argv[1])
