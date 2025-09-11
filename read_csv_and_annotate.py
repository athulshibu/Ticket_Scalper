import cv2
import numpy as np
import os
import tkinter as tk
import pandas as pd
from typing import List, Tuple

def annotate_and_save(img_path: str, centers_df: pd.DataFrame, out_path: str):
    img = cv2.imread(img_path)
    for cx, cy in centers_df[["cx","cy"]].itertuples(index=False):
        cv2.circle(img, (int(cx), int(cy)), 3, (0,0,255), -1)
    cv2.putText(img, f"Squares detected: {len(centers_df)}", (20,50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,255), 2, cv2.LINE_AA)
    cv2.imwrite(out_path, img)

if __name__ == "__main__":
    csv_file = "CGV_IMAX_square_centers.csv"
    mask_name = "CGV_IMAX_masked.png"
    df = pd.read_csv(csv_file)
    annotate_and_save(mask_name, df, "annotated.png")   

