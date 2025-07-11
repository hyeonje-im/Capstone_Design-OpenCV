import cv2
import numpy as np
from dataclasses import dataclass

@dataclass
class BoardDetectionResult:
    corners: np.ndarray
    origin: np.ndarray
    width_px: float
    height_px: float
    cm_per_px: tuple
    perspective_matrix: np.ndarray
    warped: np.ndarray
    warped_resized: np.ndarray
    grid_reference: dict | None = None 
    found: bool = True

class BoardDetector:
    def __init__(self, board_width_cm: float, board_height_cm: float, grid_width: int, grid_height: int):
        self.board_width_cm = board_width_cm
        self.board_height_cm = board_height_cm
        self._result = None
        self._locked = False
        self.grid_width = grid_width
        self.grid_height = grid_height

    def detect(self, roi_gray, detect_params):
        rect = self._detect_board(roi_gray, detect_params)
        return rect

    def process(self, frame_gray, data, rect_override=None) -> BoardDetectionResult | None:
        if self._locked:
            return self._result
        
        if rect_override is not None:
            rect = rect_override
        else:
            if not isinstance(data, (list, tuple)):
                return self._result
            rect = self._detect_board(frame_gray, data)
        
        if rect is not None:
            corners, width_px, height_px = self._get_board_pts(rect)
            origin = self._get_board_origin(corners[0])
            warped, warped_resized, perspective_matrix, warped_width_px, warped_height_px = self._warp_board(frame_gray, corners, width_px, height_px)
            cm_per_px = self._calculate_cm_per_px(warped_width_px, warped_height_px)
            
            self._result = BoardDetectionResult(
                corners=corners,
                origin=origin,
                width_px=width_px,
                height_px=height_px,
                cm_per_px=cm_per_px,
                perspective_matrix=perspective_matrix,
                warped=warped,
                warped_resized=warped_resized,
            )
            return self._result
        else:
            # print("[DEBUG] 보드 탐지 실패. 이전 결과 유지됨")
            return self._result
    
    def generate_coordinate_system(self):
        """
        보드 네 모서리(corners)를 픽셀 좌표에서
        실제 cm 단위 평면 좌표로 바로 매핑하는 H_metric과,
        그 위에 미리 계산된 그리드 중심(cell_centers)을 반환합니다.
        """
        if self._result is None:
            raise RuntimeError("Board not yet detected")

        # 1) 원본 보드 모서리 4점 (TL, TR, BR, BL)
        src_pts = self._result.corners  # shape (4,2), dtype=float32

        # 2) dst_pts를 실제 보드 크기(cm)로 정의
        dst_pts = np.array([
            [0.0,                 0.0                ],
            [self.board_width_cm, 0.0                ],
            [self.board_width_cm, self.board_height_cm],
            [0.0,                 self.board_height_cm],
        ], dtype=np.float32)

        # 3) 픽셀→cm 매핑 행렬 계산 (metric homography)
        H_metric = cv2.getPerspectiveTransform(src_pts, dst_pts)

        # 4) 그리드별 중심점(cm 단위) 생성
        cell_centers = []
        cw = self.board_width_cm  / self.grid_width
        ch = self.board_height_cm / self.grid_height
        for row in range(self.grid_height):
            for col in range(self.grid_width):
                cx = (col + 0.5) * cw
                cy = (row + 0.5) * ch
                cell_centers.append((cx, cy))

        # 5) (선택) 그리드 선분도 cm 단위로 미리 계산
        horizontal = [((0, i*ch), (self.board_width_cm, i*ch))
                    for i in range(self.grid_height+1)]
        vertical   = [((j*cw, 0), (j*cw, self.board_height_cm))
                    for j in range(self.grid_width+1)]

        return {
            "H_metric":     H_metric,
            "cell_centers": cell_centers,
            "grid_lines": {
                "horizontal": horizontal,
                "vertical":   vertical
            }
        }

    # def lock(self):
        # print("[DEBUG] lock() called")
        # if self._result is None:
        #     print("[ERROR] self._result is None → 탐지된 보드가 없음. 고정 실패")
        #     return
        # # metric homography 기반 좌표계 생성
        # self._result.grid_reference = self.generate_coordinate_system()
        # print("[DEBUG] grid_reference OK:", self._result.grid_reference is not None)
        # self._locked = True
        # print("[DEBUG] 보드 고정 완료, locked =", self._locked)

    def lock(self):
        if self._result is None:
            return

        # 1) Metric homography 기반 grid_reference 생성 및 잠금
        self._result.grid_reference = self.generate_coordinate_system()
        self._locked = True

        # 2) 이미 계산된 bird’s-eye 뷰 가져오기
        vis = self._result.warped.copy()

        # 3) 네 모서리 픽셀 좌표
        tl, tr, br, bl = self._result.corners

        # 4) 각 변의 픽셀 길이 계산
        top_len_px    = np.linalg.norm(tr - tl)
        bottom_len_px = np.linalg.norm(br - bl)
        left_len_px   = np.linalg.norm(bl - tl)
        right_len_px  = np.linalg.norm(br - tr)

        # 5) 실제 cm 대비 픽셀 스케일(cm/px) 계산
        scale_top    = self.board_width_cm  / top_len_px
        scale_bottom = self.board_width_cm  / bottom_len_px
        scale_left   = self.board_height_cm / left_len_px
        scale_right  = self.board_height_cm / right_len_px

        # 6) warp된 뷰 위에 스케일 정보 텍스트 추가
        cv2.putText(vis, f"Top: {scale_top:.2f}cm/px",    (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
        cv2.putText(vis, f"Bottom: {scale_bottom:.2f}cm/px", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
        cv2.putText(vis, f"Left: {scale_left:.2f}cm/px",    (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
        cv2.putText(vis, f"Right: {scale_right:.2f}cm/px",  (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

        # 7) 펼쳐진 보드 뷰를 창에 표시
        cv2.imshow("Warped Board Preview", vis)
        cv2.waitKey(1)

    def reset(self):
        self._locked = False
        self._result = None

    def get_result(self) -> BoardDetectionResult | None:
        return self._result
    
    #!!! 외부에서 결과를 입력 받음. 꼭 이렇게 해야할까?
    def draw(self, frame, result: BoardDetectionResult):
        if result is None:
            return

        # 기본 시각화
        cv2.drawContours(frame, [result.corners.astype(np.int32)], -1, (255, 0, 0), 2)
        cv2.circle(frame, tuple(result.origin[:2].astype(int)), 5, (0, 0, 255), -1)

        if result.grid_reference is None:
            return

        overlay = self.get_grid_overlay_points(result)
        if overlay is None:
            return

        for x, y in overlay["centers"]:
            cv2.circle(frame, (int(x), int(y)), 2, (0, 255, 0), -1)

        for pt1, pt2 in overlay["lines"]:
            cv2.line(frame, (int(pt1[0]), int(pt1[1])), (int(pt2[0]), int(pt2[1])), (0, 255, 255), 1)


    def get_grid_overlay_points(self, result):
        if result is None or result.grid_reference is None:
            return None

        # metric homography 역행렬 (cm→pixel)
        H_inv = np.linalg.inv(result.grid_reference["H_metric"])

        # cm 단위로 생성된 그리드 중심점 목록
        pts_cm = np.array(result.grid_reference["cell_centers"], dtype=np.float32).reshape(-1,1,2)

        # cm→pixel 좌표 변환
        pts_px = cv2.perspectiveTransform(pts_cm, H_inv).reshape(-1,2)

        # (선택) 선분도 동일하게 변환
        mapped_lines = []
        for segs in result.grid_reference["grid_lines"].values():
            for p1_cm, p2_cm in segs:
                seg = np.array([[p1_cm, p2_cm]], dtype=np.float32)
                p1_px, p2_px = cv2.perspectiveTransform(seg, H_inv)[0]
                mapped_lines.append((tuple(p1_px), tuple(p2_px)))

        return {"centers": pts_px, "lines": mapped_lines}


    # 내부 유틸 함수들
    def _detect_board(self, gray, data):
        brightness, min_aspect_ratio, max_aspect_ratio = data
        _, thresh = cv2.threshold(gray, brightness, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        largest_rect = None
        largest_area = 0

        for contour in contours:
            approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
            if len(approx) == 4:
                area = cv2.contourArea(approx)
                x, y, w, h = cv2.boundingRect(approx)
                aspect_ratio = float(w) / h
                if area > 500 and min_aspect_ratio < aspect_ratio < max_aspect_ratio:
                    largest_area = area
                    largest_rect = approx

        return largest_rect

    def _get_board_pts(self, rect):
            pts = rect.reshape(4, 2).astype(np.float32)
            sum_pts = pts.sum(axis=1)
            diff_pts = np.diff(pts, axis=1)
            top_left = pts[np.argmin(sum_pts)]
            bottom_right = pts[np.argmax(sum_pts)]
            top_right = pts[np.argmin(diff_pts)]
            bottom_left = pts[np.argmax(diff_pts)]

            ordered = np.array([top_left, top_right, bottom_right, bottom_left])
            width_px = np.linalg.norm(top_right - top_left)
            height_px = np.linalg.norm(bottom_left - top_left)

            return ordered, width_px, height_px

    def _calculate_cm_per_px(self, warped_width_px, warped_height_px):
        cm_per_px_x = self.board_width_cm / max(warped_width_px, 1)
        cm_per_px_y = self.board_height_cm / max(warped_height_px, 1)
        return (cm_per_px_x, cm_per_px_y)

    def _warp_board(self, frame, corners, board_width_px, board_height_px):
        dst = np.array([[0, 0], [board_width_px - 1, 0],
                    [board_width_px - 1, board_height_px - 1], [0, board_height_px - 1]], dtype="float32")
        matrix = cv2.getPerspectiveTransform(corners, dst)
        warped = cv2.warpPerspective(frame, matrix, (int(board_width_px), int(board_height_px)))
        warped_resized = cv2.resize(warped, (frame.shape[1] // 2, frame.shape[1] // 2))
        warped_board_width_px = int(np.linalg.norm(dst[1] - dst[0]))
        warped_board_height_px = int(np.linalg.norm(dst[3] - dst[0]))
        return warped, warped_resized, matrix, warped_board_width_px, warped_board_height_px
    
    def _get_board_origin(self, top_left):
        return np.array([top_left[0], top_left[1], 0], dtype=np.float32)
    
    @property
    def is_locked(self):
        return self._locked


class ROIProcessor:
    def __init__(
        self,
        clahe_clip=2.0,
        clahe_tile=(8,8),
        adaptive_block=21,
        adaptive_C=5
    ):
        self.clahe_clip = clahe_clip
        self.clahe_tile = clahe_tile
        self.adaptive_block = adaptive_block
        self.adaptive_C = adaptive_C
        self.enable_clahe = True
        self.enable_adaptive = True

    def process(self, roi):
        """
        roi: input ROI, expected grayscale or color image
        returns: preprocessed binarized ROI
        """
        if roi is None or roi.size == 0:
            raise ValueError("Empty ROI passed to ROIProcessor")

        # 1) 그레이스케일 변환
        if len(roi.shape) == 3:
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            roi_gray = roi.copy()

        # 2) CLAHE 적용 (명암 대비 향상)
        if self.enable_clahe:
            clahe = cv2.createCLAHE(
                clipLimit=self.clahe_clip,
                tileGridSize=self.clahe_tile
            )
            roi_gray = clahe.apply(roi_gray)

        # 3) Adaptive Threshold 이진화
        if self.enable_adaptive:
            block_size = max(3, self.adaptive_block)
            if block_size % 2 == 0:
                block_size += 1
            roi_bin = cv2.adaptiveThreshold(
                roi_gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                block_size,
                self.adaptive_C
            )
        else:
            _, roi_bin = cv2.threshold(roi_gray, 127, 255, cv2.THRESH_BINARY)

        # 4) 소금·후추 노이즈 제거
        roi_bin = cv2.medianBlur(roi_bin, 3)

        return roi_bin
