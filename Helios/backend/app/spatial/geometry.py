"""Normalized image-coordinate geometry helpers (x/y values in the 0..1 range)."""
from __future__ import annotations
from typing import Sequence

def box_center(box: Sequence[float]) -> tuple[float,float]: return (float(box[0])+float(box[2])/2,float(box[1])+float(box[3])/2)
def box_bottom_center(box: Sequence[float]) -> tuple[float, float]:
    """Calculate the bottom-center point of a bounding box [x, y, w, h]."""
    return (float(box[0]) + float(box[2]) / 2.0, float(box[1]) + float(box[3]))
def point_in_polygon(point: tuple[float,float], polygon: Sequence[Sequence[float]]) -> bool:
    x,y=point; inside=False
    for index,current in enumerate(polygon):
        previous=polygon[index-1]; x1,y1=map(float,current);x2,y2=map(float,previous)
        if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: inside=not inside
    return inside

