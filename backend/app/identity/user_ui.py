"""
LiftGuard AI - User Profile UI Overlay
=======================================
Draws the user identification panel on the main video frame.
"""
 
import cv2
import numpy as np
from datetime import datetime
 
 
class UserUIOverlay:
    """
    Renders the user identification panel on the video output frame.
    Call draw() each frame from _draw_full_ui().
    """
 
    def __init__(self):
        self.show_history   = False
        self.history_cache  = []
        self.last_history_t = 0
 
    def draw(
        self,
        img: np.ndarray,
        user_profile,
        panel_x: int,
        panel_y: int,
        panel_w: int = 280,
        id_state: str = "identified"
    ) -> int:
        """
        Draw user profile panel.
 
        Args:
            img:          Frame to draw on
            user_profile: UserProfile object
            panel_x/y:   Top-left corner
            panel_w:      Panel width
            id_state:     'scanning' | 'confirming' | 'identified' | 'guest'
 
        Returns: bottom Y coordinate
        """
        panel_h = 115
 
        # ── Background ────────────────────────────────────────
        cv2.rectangle(img, (panel_x, panel_y),
                      (panel_x + panel_w, panel_y + panel_h),
                      (20, 20, 20), -1)
 
        # ── Border color by state ─────────────────────────────
        if   id_state == "identified": border = (0, 255, 0)
        elif id_state == "confirming": border = (0, 255, 255)
        elif id_state == "scanning":   border = (0, 165, 255)
        else:                          border = (100, 100, 100)   # guest
 
        cv2.rectangle(img, (panel_x, panel_y),
                      (panel_x + panel_w, panel_y + panel_h),
                      border, 2)
 
        # ── Avatar circle ─────────────────────────────────────
        avatar_cx = panel_x + 30
        avatar_cy = panel_y + 40
        cv2.circle(img, (avatar_cx, avatar_cy), 22, border, -1)
 
        if user_profile and not user_profile.is_guest:
            initials = "".join(
                w[0].upper()
                for w in user_profile.display_name.split()[:2]
            )
        else:
            initials = "G"
 
        (tw, th), _ = cv2.getTextSize(
            initials, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2
        )
        cv2.putText(
            img, initials,
            (avatar_cx - tw // 2, avatar_cy + th // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2
        )
 
        # ── Name & status ─────────────────────────────────────
        tx = panel_x + 60
 
        if user_profile and not user_profile.is_guest:
            name = user_profile.display_name[:20]
            cv2.putText(img, name,
                        (tx, panel_y + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (255, 255, 255), 1)
 
            sid_text = f"ID #{user_profile.user_id}"
            cv2.putText(img, sid_text,
                        (tx, panel_y + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (160, 160, 160), 1)
 
            sess_text = f"Sessions: {user_profile.total_sessions}"
            cv2.putText(img, sess_text,
                        (tx, panel_y + 62),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (140, 140, 140), 1)
 
            # Last seen
            if user_profile.last_seen:
                try:
                    dt  = datetime.fromisoformat(user_profile.last_seen)
                    ago = (datetime.now() - dt).days
                    ls  = f"Last: {ago}d ago" if ago > 0 else "Last: today"
                except Exception:
                    ls  = ""
                cv2.putText(img, ls,
                            (tx, panel_y + 79),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                            (120, 120, 120), 1)
        else:
            # Guest
            cv2.putText(img, "Guest Mode",
                        (tx, panel_y + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (180, 180, 180), 1)
            cv2.putText(img, "No profile loaded",
                        (tx, panel_y + 52),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (120, 120, 120), 1)
 
        # ── State badge ───────────────────────────────────────
        state_labels = {
            "identified": "✓ IDENTIFIED",
            "confirming": "CONFIRMING...",
            "scanning":   "SCANNING...",
            "guest":      "GUEST"
        }
        state_label = state_labels.get(id_state, id_state.upper())
        cv2.putText(img, state_label,
                    (panel_x + 15, panel_y + panel_h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                    border, 1)
 
        return panel_y + panel_h
 
    def draw_scanning_overlay(
        self,
        img: np.ndarray,
        face_locations: list,
        id_count: int,
        confirm_needed: int,
        candidate_name: str = None
    ):
        """
        Draw face-detection boxes and progress indicator
        during live scanning (outside the main UI panels).
        """
        for top, right, bottom, left in face_locations:
            progress = id_count / max(confirm_needed, 1)
            color    = (
                (0, 255, 0) if progress > 0.8
                else (0, 255, 255) if progress > 0.4
                else (0, 165, 255)
            )
 
            # Dashed/solid box
            cv2.rectangle(img, (left, top), (right, bottom), color, 2)
 
            # Corner accents
            corner_len = 20
            corners = [
                ((left, top),          (1, 1)),
                ((right, top),         (-1, 1)),
                ((left, bottom),       (1, -1)),
                ((right, bottom),      (-1, -1)),
            ]
            for (cx, cy), (dx, dy) in corners:
                cv2.line(img,
                         (cx, cy),
                         (cx + dx * corner_len, cy),
                         color, 3)
                cv2.line(img,
                         (cx, cy),
                         (cx, cy + dy * corner_len),
                         color, 3)
 
            # Name label
            label = candidate_name if candidate_name else "Scanning..."
            cv2.putText(img, label,
                        (left, top - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        color, 2)
 
            # Mini progress bar beneath face box
            if id_count > 0:
                bar_w    = right - left
                filled_w = int(bar_w * progress)
                cv2.rectangle(img,
                              (left, bottom + 5),
                              (right, bottom + 15),
                              (50, 50, 50), -1)
                cv2.rectangle(img,
                              (left, bottom + 5),
                              (left + filled_w, bottom + 15),
                              color, -1)
