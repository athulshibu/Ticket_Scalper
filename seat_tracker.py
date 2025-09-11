import cv2
import numpy as np
import os
import tkinter as tk
import pandas as pd
from typing import List, Tuple

def resize_to_screen(img, screen_w=None, screen_h=None):
    if screen_w is None or screen_h is None:
        root = tk.Tk()
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
    return cv2.resize(img, (screen_h, screen_w), interpolation=cv2.INTER_NEAREST)

def make_range_bgr(color_bgr, tol):
    lower = np.array([max(0, c - tol) for c in color_bgr], dtype=np.uint8)
    upper = np.array([min(255, c + tol) for c in color_bgr], dtype=np.uint8)
    return lower, upper

def mask_two_colors(image_path, color1_rgb=(141,166,241), color2_rgb=(172,172,171),
                    tol=12, out_path="masked.png", screen_w=1600, screen_h=2560):
    img = cv2.imread(image_path)
    img = resize_to_screen(img, screen_w, screen_h)

    color1_bgr = color1_rgb[::-1]
    color2_bgr = color2_rgb[::-1]

    lower1, upper1 = make_range_bgr(color1_bgr, tol)
    lower2, upper2 = make_range_bgr(color2_bgr, tol)

    mask1 = cv2.inRange(img, lower1, upper1)
    mask2 = cv2.inRange(img, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)

    cv2.imwrite(out_path, mask)
    print(f"Mask saved at {out_path}")
    return mask

def detect_seat_centers_watershed(mask_img_path: str) -> pd.DataFrame:
    """Split merged white squares with watershed, then return centers."""
    img = cv2.imread(mask_img_path)
    if img is None:
        raise FileNotFoundError(mask_img_path)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Binary (seats are already bright in your masked images)
    _, bw = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    # Clean up small gaps, keep seats separated but not eroded away
    k = np.ones((3,3), np.uint8)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, k, iterations=1)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, k, iterations=1)

    # --- Watershed split ---
    dist = cv2.distanceTransform(bw, cv2.DIST_L2, 3)
    dist_norm = cv2.normalize(dist, None, 0, 1.0, cv2.NORM_MINMAX)
    # Peaks for markers (0.40–0.50 of max works well for these seats)
    _, peaks = cv2.threshold((dist_norm * 255).astype(np.uint8), 110, 255, cv2.THRESH_BINARY)
    peaks = cv2.morphologyEx(peaks, cv2.MORPH_OPEN, k, iterations=1)

    num_markers, markers = cv2.connectedComponents(peaks)
    markers = markers + 1
    markers[bw == 0] = 0
    cv2.watershed(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), markers)

    rows: List[Tuple[int,int,int,int,float]] = []
    for lbl in range(2, markers.max() + 1):
        m = (markers == lbl).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        if area < 30:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        ar = w / float(h)
        if not (0.65 <= ar <= 1.35):  # square-ish
            continue
        M = cv2.moments(cnt)
        if M["m00"] == 0: 
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        if cx < 1400:
            rows.append((cx, cy, w, h, float(area)))

    return pd.DataFrame(rows, columns=["cx", "cy", "w", "h", "area_px"])

def annotate_and_save(img_path: str, centers_df: pd.DataFrame, out_path: str):
    img = cv2.imread(img_path)
    for cx, cy in centers_df[["cx","cy"]].itertuples(index=False):
        cv2.circle(img, (int(cx), int(cy)), 3, (0,0,255), -1)
    cv2.putText(img, f"Squares detected: {len(centers_df)}", (20,50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,255), 2, cv2.LINE_AA)
    cv2.imwrite(out_path, img)


if __name__ == "__main__":
    # theatre_names = ["BCC_1", "CGV_IMAX", "Lotte_5"]
    # theatre_names = ["BCC_1", "Lotte_5"]
    theatre_names = ["CGV_IMAX"]    

    for theatre_name in theatre_names:
        image = os.path.join("Theatres", theatre_name+".png")
        out_path = theatre_name + "_masked.png"
        mask_two_colors(image, tol=14, screen_w=1600, screen_h=2560, out_path=out_path)

    for theatre_name in theatre_names:
        mask_name = theatre_name + "_masked.png"
        # df = find_white_square_centers(mask_name)
        df = detect_seat_centers_watershed(mask_name)
        df.to_csv(f"{theatre_name}_square_centers.csv", index=False)
        annotate_and_save(mask_name, df, f"{theatre_name}_annotated.png")