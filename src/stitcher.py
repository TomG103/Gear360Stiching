import cv2
import numpy as np
import os
import json
import logging

class Gear360Stitcher:
    def __init__(self, camera_model="Gear 360 (2017)"):
        self.camera_model = camera_model

        # Default parameters
        if camera_model == "Gear 360 (2017)":
            self.src_width = 5472
            self.src_height = 2736
            self.radius = 1350
            self.fov = 195.0

            self.cx1 = 1368
            self.cy1 = 1368
            self.cx2 = 4104
            self.cy2 = 1368

        else: # 2016 model SM-C200
            self.src_width = 7776
            self.src_height = 3888
            self.radius = 1910
            self.fov = 195.0
            self.cx1 = 1944
            self.cy1 = 1944
            self.cx2 = 5832
            self.cy2 = 1944

        self.out_width = self.src_width
        self.out_height = self.src_width // 2

        self.map1_x = None
        self.map1_y = None
        self.map2_x = None
        self.map2_y = None

        # Misalignment parameters for lens 2
        self.yaw2 = 0.0
        self.pitch2 = 0.0
        self.roll2 = 0.0

        self.calibration_file = "calibration.json"
        self.load_calibration()

    def load_calibration(self):
        if os.path.exists(self.calibration_file):
            try:
                with open(self.calibration_file, "r") as f:
                    calib = json.load(f)
                    if self.camera_model in calib:
                        c = calib[self.camera_model]
                        self.yaw2 = c.get("yaw2", 0.0)
                        self.pitch2 = c.get("pitch2", 0.0)
                        self.roll2 = c.get("roll2", 0.0)
                        logging.info(f"Loaded calibration for {self.camera_model}")
            except Exception as e:
                logging.error(f"Error loading calibration: {e}")

    def save_calibration(self):
        calib = {}
        if os.path.exists(self.calibration_file):
            try:
                with open(self.calibration_file, "r") as f:
                    calib = json.load(f)
            except:
                pass

        calib[self.camera_model] = {
            "yaw2": float(self.yaw2),
            "pitch2": float(self.pitch2),
            "roll2": float(self.roll2)
        }
        try:
            with open(self.calibration_file, "w") as f:
                json.dump(calib, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving calibration: {e}")

    def update_maps(self, width=None, height=None):
        if width is not None:
            self.out_width = width
        if height is not None:
            self.out_height = height

        # Optimization: Skip expensive recomputation if parameters haven't changed
        current_params = (self.out_width, self.out_height, self.yaw2, self.pitch2, self.roll2)
        if getattr(self, '_last_map_params', None) == current_params and self.map1_x is not None:
            return
        self._last_map_params = current_params

        W = self.out_width
        H = self.out_height

        # Create a grid of coordinates
        u, v = np.meshgrid(np.arange(W), np.arange(H))

        # Longitude and Latitude
        lon = (u / W - 0.5) * 2 * np.pi
        lat = -(v / H - 0.5) * np.pi

        # 3D points on sphere
        X = np.cos(lat) * np.sin(lon)
        Y = np.sin(lat)
        Z = np.cos(lat) * np.cos(lon)

        # Front Lens (facing +Z)
        x1 = X
        y1 = Y
        z1 = Z

        theta1 = np.arccos(np.clip(z1, -1.0, 1.0))
        r1 = (self.radius / (self.fov / 2.0 * np.pi / 180.0)) * theta1

        mask1 = theta1 <= (self.fov / 2.0 * np.pi / 180.0)

        rho1 = np.sqrt(x1**2 + y1**2)
        rho1[rho1 == 0] = 1e-5

        map1_x = self.cx1 + r1 * (x1 / rho1)
        map1_y = self.cy1 - r1 * (y1 / rho1)

        map1_x[~mask1] = -1
        map1_y[~mask1] = -1

        self.map1_x = map1_x.astype(np.float32)
        self.map1_y = map1_y.astype(np.float32)

        # Back Lens (facing -Z)
        # Apply misalignment
        R_yaw = np.array([
            [np.cos(self.yaw2), 0, np.sin(self.yaw2)],
            [0, 1, 0],
            [-np.sin(self.yaw2), 0, np.cos(self.yaw2)]
        ])
        R_pitch = np.array([
            [1, 0, 0],
            [0, np.cos(self.pitch2), -np.sin(self.pitch2)],
            [0, np.sin(self.pitch2), np.cos(self.pitch2)]
        ])
        R_roll = np.array([
            [np.cos(self.roll2), -np.sin(self.roll2), 0],
            [np.sin(self.roll2), np.cos(self.roll2), 0],
            [0, 0, 1]
        ])

        R_total = R_yaw @ R_pitch @ R_roll

        # Base frame for back lens
        x2_base = -X
        y2_base = Y
        z2_base = -Z

        pts2 = np.stack((x2_base, y2_base, z2_base), axis=-1)
        pts2_rot = pts2 @ R_total.T

        x2 = pts2_rot[..., 0]
        y2 = pts2_rot[..., 1]
        z2 = pts2_rot[..., 2]

        theta2 = np.arccos(np.clip(z2, -1.0, 1.0))
        r2 = (self.radius / (self.fov / 2.0 * np.pi / 180.0)) * theta2

        mask2 = theta2 <= (self.fov / 2.0 * np.pi / 180.0)

        rho2 = np.sqrt(x2**2 + y2**2)
        rho2[rho2 == 0] = 1e-5

        map2_x = self.cx2 + r2 * (x2 / rho2)
        map2_y = self.cy2 - r2 * (y2 / rho2)

        map2_x[~mask2] = -1
        map2_y[~mask2] = -1

        self.map2_x = map2_x.astype(np.float32)
        self.map2_y = map2_y.astype(np.float32)

        # Create blending masks
        self.mask1 = mask1.astype(np.float32)
        self.mask2 = mask2.astype(np.float32)

        # Calculate overlap region and blending weights
        overlap = np.logical_and(mask1, mask2)

        self.blend_w1 = self.mask1.copy()
        self.blend_w2 = self.mask2.copy()

        # Simple linear blending in overlap region based on longitude
        # The overlap happens near x = W/4 and x = 3W/4
        # We can create a smooth transition
        for i in range(H):
            # Left overlap (around W/4)
            overlap_idx = np.where(overlap[i, :])[0]
            if len(overlap_idx) > 0:
                # Find clusters of overlap (left and right seams)
                diffs = np.diff(overlap_idx)
                split_points = np.where(diffs > 1)[0]

                if len(split_points) > 0:
                    left_seam = overlap_idx[:split_points[0]+1]
                    right_seam = overlap_idx[split_points[0]+1:]

                    if len(left_seam) > 0:
                        n = len(left_seam)
                        # Lens 2 is on the left edge of equirectangular (0 to W/4)
                        # Lens 1 is in the middle (W/4 to 3W/4)
                        # So at left seam, going from left to right, we transition from Lens 2 to Lens 1
                        weights = np.linspace(0, 1, n)
                        self.blend_w1[i, left_seam] = weights
                        self.blend_w2[i, left_seam] = 1.0 - weights

                    if len(right_seam) > 0:
                        n = len(right_seam)
                        # At right seam, going from left to right, we transition from Lens 1 to Lens 2
                        weights = np.linspace(1, 0, n)
                        self.blend_w1[i, right_seam] = weights
                        self.blend_w2[i, right_seam] = 1.0 - weights
                else:
                    # Just one contiguous overlap? (Shouldn't happen for 360, but fallback)
                    n = len(overlap_idx)
                    if overlap_idx[0] < W // 2:
                        weights = np.linspace(0, 1, n)
                        self.blend_w1[i, overlap_idx] = weights
                        self.blend_w2[i, overlap_idx] = 1.0 - weights
                    else:
                        weights = np.linspace(1, 0, n)
                        self.blend_w1[i, overlap_idx] = weights
                        self.blend_w2[i, overlap_idx] = 1.0 - weights

        # Normalize weights
        sum_w = self.blend_w1 + self.blend_w2
        sum_w[sum_w == 0] = 1.0
        self.blend_w1 /= sum_w
        self.blend_w2 /= sum_w

        # Convert weights to 3 channels for easy multiplication
        self.blend_w1 = np.repeat(self.blend_w1[:, :, np.newaxis], 3, axis=2)
        self.blend_w2 = np.repeat(self.blend_w2[:, :, np.newaxis], 3, axis=2)

    def stitch(self, image):
        if self.map1_x is None:
            self.update_maps()

        img1 = cv2.remap(image, self.map1_x, self.map1_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
        img2 = cv2.remap(image, self.map2_x, self.map2_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

        blended = img1 * self.blend_w1 + img2 * self.blend_w2
        return blended.astype(np.uint8)

    def find_misalignment(self, image):
        # We need to find the best yaw, pitch, roll for lens 2
        # A simple approach: use ORB features on the remapped images (without blending)

        # First, generate maps with 0 misalignment
        old_yaw, old_pitch, old_roll = self.yaw2, self.pitch2, self.roll2
        self.yaw2 = 0.0
        self.pitch2 = 0.0
        self.roll2 = 0.0
        self.update_maps()

        img1 = cv2.remap(image, self.map1_x, self.map1_y, cv2.INTER_LINEAR)
        img2 = cv2.remap(image, self.map2_x, self.map2_y, cv2.INTER_LINEAR)

        # Convert to grayscale
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        # Find overlap mask
        overlap = np.logical_and(self.mask1, self.mask2)
        overlap_uint8 = overlap.astype(np.uint8) * 255

        # Feature detection
        orb = cv2.ORB_create(nfeatures=1000)
        kp1, des1 = orb.detectAndCompute(gray1, overlap_uint8)
        kp2, des2 = orb.detectAndCompute(gray2, overlap_uint8)

        if des1 is None or des2 is None or len(des1) < 10 or len(des2) < 10:
            logging.warning("Not enough features found for dynamic alignment.")
            self.yaw2, self.pitch2, self.roll2 = old_yaw, old_pitch, old_roll
            self.update_maps()
            return False

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)

        good_matches = matches[:50]

        if len(good_matches) < 10:
            logging.warning("Not enough good matches found for dynamic alignment.")
            self.yaw2, self.pitch2, self.roll2 = old_yaw, old_pitch, old_roll
            self.update_maps()
            return False

        pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
        pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])

        # Calculate the average displacement
        diff = pts1 - pts2
        avg_dx = np.median(diff[:, 0])
        avg_dy = np.median(diff[:, 1])

        # Convert pixel displacement to angles
        # W = 2*pi, H = pi
        yaw_offset = (avg_dx / self.out_width) * 2 * np.pi
        pitch_offset = (avg_dy / self.out_height) * np.pi

        # This is a very rough approximation. For true alignment,
        # we'd need optimization. Let's start with this simple offset.
        self.yaw2 -= yaw_offset
        self.pitch2 -= pitch_offset

        # Refine map
        self.update_maps()
        return True

if __name__ == "__main__":
    # Test initialization
    stitcher = Gear360Stitcher()
    # Create a dummy image
    img = np.zeros((2736, 5472, 3), dtype=np.uint8)
    stitcher.update_maps(1024, 512)
    out = stitcher.stitch(img)
    print("Stitcher test successful, output shape:", out.shape)
