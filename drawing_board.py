"""
DrawingBoard v1.2
Author QQ: 331701160
License: MIT

A drawing board with mouse-following auto-draw modes:
- Archimedean spiral (compact)
- Brownian motion
- Random-radius circle (counterclockwise, ~1 cm/s)
- Gradient brush (10 cm transition)
- 777 mechanism (7.77% chance after 10s continuous mouse move)
"""

import pygame
import sys
import math
import random
import threading
import socket
import time
from collections import deque

# ── Constants ──────────────────────────────────────────────
WINDOW_WIDTH = 1080
WINDOW_HEIGHT = 920
PORT = 11451
FPS = 60
IDLE_MIN = 10
IDLE_MAX = 39

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (220, 40, 40)
BLUE = (40, 80, 220)
GRAY = (160, 160, 160)
PINK = (255, 180, 180)
GREEN = (40, 180, 80)
ORANGE = (240, 140, 40)


class DrawingBoard:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("DrawingBoard v1.2")
        self.clock = pygame.time.Clock()
        self.running = True

        # ── Mouse state ─────────────────────────────────
        self.mouse_pos = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        self.last_mouse_pos = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        self.drawing = False          # left mouse button held
        self.mouse_moving = False
        self.last_move_time = time.time()
        self.idle_threshold = random.uniform(IDLE_MIN, IDLE_MAX)

        # Track the last point of manual drawing for auto-draw origin
        self.last_manual_point = None

        # ── Drawing surfaces ────────────────────────────
        self.user_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.user_surface.fill(WHITE)

        self.auto_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.auto_surface.fill(WHITE)
        self.auto_surface.set_colorkey(WHITE)

        # ── Boundary / cache system ─────────────────────
        bw, bh = WINDOW_WIDTH // 3, WINDOW_HEIGHT // 3
        self.boundary_rect = pygame.Rect(
            WINDOW_WIDTH // 2 - bw // 2,
            WINDOW_HEIGHT // 2 - bh // 2,
            bw, bh,
        )
        self.cache_left = deque(maxlen=800)
        self.cache_right = deque(maxlen=800)
        self.cache_top = deque(maxlen=800)
        self.cache_bottom = deque(maxlen=800)

        # ── User draw points ────────────────────────────
        self.draw_points = deque(maxlen=20000)
        self.last_draw_pos = None
        self.brush_color = BLACK  # current manual brush color

        # ── Gradient state (shared by manual + auto) ────
        self.gradient_active = False
        self.gradient_from = BLACK
        self.gradient_to = BLACK
        self.gradient_remaining = 0.0   # px remaining in gradient (total = 10 cm)

        # ── 777 mechanism ───────────────────────────────
        self.continuous_move_start = 0.0  # timestamp when mouse started moving
        self.checked_777 = False

        # ── Auto-draw state ─────────────────────────────
        self.auto_drawing = False
        self.auto_type = None  # "spiral" | "brownian" | "circle"
        self.auto_origin = [WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2]
        self.spiral_angle = 0.0
        self.spiral_radius = 0.0
        self.brownian_pos = [float(WINDOW_WIDTH // 2), float(WINDOW_HEIGHT // 2)]
        self.circle_angle = 0.0
        self.circle_radius = 50.0
        self.circle_center = [float(WINDOW_WIDTH // 2), float(WINDOW_HEIGHT // 2)]
        self.auto_last_pos = None  # incremental draw tracker
        self.auto_color = BLUE

        # ── Network server ──────────────────────────────
        self.server_running = True
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

        # ── Font ────────────────────────────────────────
        self.font = pygame.font.Font(None, 22)

    # ═══════════════════════════════════════════════════════
    #  NETWORK SERVER
    # ═══════════════════════════════════════════════════════
    def _run_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("0.0.0.0", PORT))
            server.listen(1)
            server.settimeout(1.0)
        except OSError as e:
            print(f"[server] bind failed: {e}")
            return
        print(f"[server] listening on port {PORT}")
        while self.server_running:
            try:
                conn, addr = server.accept()
                data = conn.recv(4096).decode("utf-8", errors="ignore")
                if data:
                    self._handle_command(data.strip())
                conn.close()
            except socket.timeout:
                continue
            except Exception:
                if self.server_running:
                    continue
        server.close()

    def _handle_command(self, cmd):
        print(f"[server] received: {cmd}")
        c = cmd.lower()
        if c == "clear":
            self.user_surface.fill(WHITE)
            self.auto_surface.fill(WHITE)
            self.draw_points.clear()
            self.auto_last_pos = None
            self.last_manual_point = None
            self.cache_left.clear()
            self.cache_right.clear()
            self.cache_top.clear()
            self.cache_bottom.clear()
        elif c == "pause":
            self.auto_drawing = False
        elif c == "quit":
            self.running = False

    # ═══════════════════════════════════════════════════════
    #  BOUNDARY / CACHE MANAGEMENT
    # ═══════════════════════════════════════════════════════
    def _update_boundary_and_cache(self):
        mx, my = self.mouse_pos
        bw = self.boundary_rect.width
        bh = self.boundary_rect.height

        # horizontal boundary
        if mx < self.boundary_rect.left:
            self.cache_right.clear()
            self.boundary_rect.left = max(0, mx - bw // 4)
            self.boundary_rect.width = bw
        elif mx > self.boundary_rect.right:
            self.cache_left.clear()
            self.boundary_rect.right = min(WINDOW_WIDTH, mx + bw // 4)
            self.boundary_rect.width = bw

        # vertical boundary
        if my < self.boundary_rect.top:
            self.cache_bottom.clear()
            self.boundary_rect.top = max(0, my - bh // 4)
            self.boundary_rect.bottom = self.boundary_rect.top + bh
        elif my > self.boundary_rect.bottom:
            self.cache_top.clear()
            self.boundary_rect.top = max(0, my - bh // 4)
            self.boundary_rect.bottom = self.boundary_rect.top + bh

        # clamp
        if self.boundary_rect.left < 0:
            self.boundary_rect.left = 0
        if self.boundary_rect.right > WINDOW_WIDTH:
            self.boundary_rect.right = WINDOW_WIDTH
        if self.boundary_rect.top < 0:
            self.boundary_rect.top = 0
        if self.boundary_rect.bottom > WINDOW_HEIGHT:
            self.boundary_rect.bottom = WINDOW_HEIGHT

        # feed cache
        if self.mouse_moving:
            self.cache_left.append((mx, my))
            self.cache_right.append((mx, my))
            self.cache_top.append((mx, my))
            self.cache_bottom.append((mx, my))

    # ═══════════════════════════════════════════════════════
    #  AUTO-DRAW MODES  (incremental — draw directly on surface)
    # ═══════════════════════════════════════════════════════

    def _spiral_step(self):
        self.spiral_angle += 0.06
        self.spiral_radius += 0.18
        ox, oy = self.auto_origin
        x = ox + self.spiral_radius * math.cos(self.spiral_angle)
        y = oy + self.spiral_radius * math.sin(self.spiral_angle)
        x = max(1, min(WINDOW_WIDTH - 2, x))
        y = max(1, min(WINDOW_HEIGHT - 2, y))
        if self.spiral_radius > 260:
            self._reset_spiral()
        return (int(x), int(y))

    def _reset_spiral(self):
        # start a new spiral from the last drawn point
        if self.auto_last_pos is not None:
            self.auto_origin = [self.auto_last_pos[0], self.auto_last_pos[1]]
        else:
            self.auto_origin = [
                random.randint(120, WINDOW_WIDTH - 120),
                random.randint(120, WINDOW_HEIGHT - 120),
            ]
        self.spiral_radius = 0.0
        self.spiral_angle = random.uniform(0, 2.0 * math.pi)

    def _brownian_step(self):
        dx = random.gauss(0, 3.5)
        dy = random.gauss(0, 3.5)
        self.brownian_pos[0] += dx
        self.brownian_pos[1] += dy
        if self.brownian_pos[0] < 5:
            self.brownian_pos[0] = 5
        if self.brownian_pos[0] >= WINDOW_WIDTH - 5:
            self.brownian_pos[0] = WINDOW_WIDTH - 5
        if self.brownian_pos[1] < 5:
            self.brownian_pos[1] = 5
        if self.brownian_pos[1] >= WINDOW_HEIGHT - 5:
            self.brownian_pos[1] = WINDOW_HEIGHT - 5
        return (int(self.brownian_pos[0]), int(self.brownian_pos[1]))

    def _circle_step(self):
        r = self.circle_radius
        dtheta = 38.0 / (r * 60.0)
        self.circle_angle += dtheta
        cx, cy = self.circle_center
        x = cx + r * math.cos(self.circle_angle)
        y = cy - r * math.sin(self.circle_angle)
        x = max(1, min(WINDOW_WIDTH - 2, x))
        y = max(1, min(WINDOW_HEIGHT - 2, y))
        if self.circle_angle >= 2.0 * math.pi:
            self._reset_circle()
        return (int(x), int(y))

    def _reset_circle(self):
        if self.auto_last_pos is not None:
            self.circle_center = [float(self.auto_last_pos[0]), float(self.auto_last_pos[1])]
        self.circle_radius = random.uniform(25, 180)
        self.circle_angle = 0.0

    def _auto_draw_step(self):
        # get new point from active mode
        if self.auto_type == "spiral":
            pt = self._spiral_step()
        elif self.auto_type == "brownian":
            pt = self._brownian_step()
        elif self.auto_type == "circle":
            pt = self._circle_step()
        else:
            return

        # incremental draw: line from last position to new position
        if self.auto_last_pos is not None:
            seg_dist = math.hypot(
                pt[0] - self.auto_last_pos[0],
                pt[1] - self.auto_last_pos[1],
            )
            gc = self._consume_gradient(seg_dist)
            color = gc if gc is not None else self.auto_color
            pygame.draw.line(self.auto_surface, color,
                             self.auto_last_pos, pt, 2)
        else:
            gc = self._gradient_color()
            color = gc if gc is not None else self.auto_color
            pygame.draw.circle(self.auto_surface, color, pt, 1)
        self.auto_last_pos = pt

    def _start_auto_draw(self):
        self.auto_drawing = True
        self.auto_type = random.choice(["spiral", "brownian", "circle"])
        # start from last manual drawing point, or auto_last_pos, or mouse position
        if self.last_manual_point is not None:
            ox, oy = self.last_manual_point
        elif self.auto_last_pos is not None:
            ox, oy = self.auto_last_pos
        else:
            ox, oy = self.mouse_pos
        self.auto_origin = [ox, oy]
        self.brownian_pos = [float(ox), float(oy)]
        self.spiral_radius = 0.0
        self.spiral_angle = random.uniform(0, 2.0 * math.pi)
        self.circle_center = [float(ox), float(oy)]
        self.circle_radius = random.uniform(25, 180)
        self.circle_angle = 0.0
        self.auto_last_pos = (ox, oy)  # seed incremental drawing
        colors = {"spiral": BLUE, "brownian": GREEN, "circle": ORANGE}
        self.auto_color = colors.get(self.auto_type, BLUE)
        print(f"[auto-draw] mode={self.auto_type} origin=({ox},{oy})")

    def _stop_auto_draw(self):
        if self.auto_drawing:
            print("[auto-draw] stopped")
        self.auto_drawing = False
        self.auto_type = None
        self.idle_threshold = random.uniform(IDLE_MIN, IDLE_MAX)

    # ═══════════════════════════════════════════════════════
    #  GRADIENT SYSTEM
    # ═══════════════════════════════════════════════════════
    GRADIENT_LENGTH = 378  # 10 cm at 96 DPI

    def _start_gradient(self, from_color, to_color=None):
        """Begin a 10 cm gradient transition."""
        if to_color is None:
            to_color = (random.randint(0, 255),
                        random.randint(0, 255),
                        random.randint(0, 255))
        self.gradient_active = True
        self.gradient_from = from_color
        self.gradient_to = to_color
        self.gradient_remaining = self.GRADIENT_LENGTH
        print(f"[gradient] {from_color} -> {to_color}")

    def _gradient_color(self):
        """Return the current interpolated color along the gradient."""
        if not self.gradient_active:
            return None  # caller uses its own default color
        t = 1.0 - (self.gradient_remaining / self.GRADIENT_LENGTH)
        t = max(0.0, min(1.0, t))
        r = int(self.gradient_from[0] + (self.gradient_to[0] - self.gradient_from[0]) * t)
        g = int(self.gradient_from[1] + (self.gradient_to[1] - self.gradient_from[1]) * t)
        b = int(self.gradient_from[2] + (self.gradient_to[2] - self.gradient_from[2]) * t)
        return (r, g, b)

    def _consume_gradient(self, dist):
        """Report distance traveled; returns the color to use for this segment."""
        c = self._gradient_color()
        if c is None:
            return None
        self.gradient_remaining -= dist
        if self.gradient_remaining <= 0:
            self.gradient_active = False
            self.gradient_remaining = 0
            # final color is the target
            return self.gradient_to
        return c

    # ═══════════════════════════════════════════════════════
    #  EVENT HANDLING
    # ═══════════════════════════════════════════════════════
    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.drawing = True
                    self.last_draw_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.drawing = False
                    # record the end point of manual drawing
                    if self.last_draw_pos is not None:
                        self.last_manual_point = self.last_draw_pos
                    self.last_draw_pos = None

            elif event.type == pygame.MOUSEMOTION:
                self.mouse_pos = event.pos
                if self.drawing:
                    if self.last_draw_pos is not None:
                        seg_dist = math.hypot(
                            event.pos[0] - self.last_draw_pos[0],
                            event.pos[1] - self.last_draw_pos[1],
                        )
                        gc = self._consume_gradient(seg_dist)
                        color = gc if gc is not None else self.brush_color
                        pygame.draw.line(
                            self.user_surface, color,
                            self.last_draw_pos, event.pos, 2,
                        )
                    self.draw_points.append(event.pos)
                    self.last_draw_pos = event.pos
                    self.last_manual_point = event.pos

                if event.pos != self.last_mouse_pos:
                    self.mouse_moving = True
                    self.last_move_time = time.time()
                    self.last_mouse_pos = event.pos
                    if self.auto_drawing:
                        self._stop_auto_draw()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_c:
                    self.user_surface.fill(WHITE)
                    self.auto_surface.fill(WHITE)
                    self.draw_points.clear()
                    self.auto_last_pos = None
                    self.last_manual_point = None
                elif event.key == pygame.K_SPACE:
                    if self.auto_drawing:
                        self._stop_auto_draw()
                    else:
                        self._start_auto_draw()
                elif event.key == pygame.K_p:
                    self.brush_color = (
                        random.randint(0, 255),
                        random.randint(0, 255),
                        random.randint(0, 255),
                    )
                elif event.key == pygame.K_o:
                    self._start_gradient(self.brush_color)
                elif event.key == pygame.K_ESCAPE:
                    self.running = False

    # ═══════════════════════════════════════════════════════
    #  UPDATE
    # ═══════════════════════════════════════════════════════
    def _update(self):
        idle_time = time.time() - self.last_move_time

        # mouse considered stopped after 0.3s of no movement
        if idle_time > 0.3:
            self.mouse_moving = False
            self.checked_777 = False

        # track continuous mouse movement for 777 mechanism
        if self.mouse_moving:
            if self.continuous_move_start == 0.0:
                self.continuous_move_start = time.time()
            move_duration = time.time() - self.continuous_move_start
            if move_duration >= 10.0 and not self.checked_777:
                self.checked_777 = True
                if random.random() < 0.0777:
                    # trigger: random color + gradient on current brush
                    new_color = (random.randint(0, 255),
                                 random.randint(0, 255),
                                 random.randint(0, 255))
                    if self.auto_drawing:
                        self._start_gradient(self.auto_color, new_color)
                        self.auto_color = new_color
                    else:
                        self._start_gradient(self.brush_color, new_color)
                        self.brush_color = new_color
                    print("[777] gradient triggered!")
        else:
            self.continuous_move_start = 0.0
            self.checked_777 = False

        # trigger auto-draw after idle threshold
        can_auto = (
            not self.mouse_moving
            and not self.drawing
            and idle_time >= self.idle_threshold
            and not self.auto_drawing
        )
        if can_auto:
            self._start_auto_draw()

        if self.auto_drawing:
            self._auto_draw_step()

        self._update_boundary_and_cache()

    # ═══════════════════════════════════════════════════════
    #  RENDER
    # ═══════════════════════════════════════════════════════
    def _render(self):
        self.screen.fill(WHITE)

        # layer 1: user drawing
        self.screen.blit(self.user_surface, (0, 0))

        # layer 2: boundary rectangle
        pygame.draw.rect(self.screen, GRAY, self.boundary_rect, 1)

        # layer 3: cache trail dots
        if self.cache_left:
            for pt in list(self.cache_left)[-30:]:
                pygame.draw.circle(self.screen, PINK, pt, 2)
        if self.cache_right:
            for pt in list(self.cache_right)[-30:]:
                pygame.draw.circle(self.screen, PINK, pt, 2)

        # layer 4: auto-draw
        self.screen.blit(self.auto_surface, (0, 0))

        # layer 5: crosshair
        mx, my = self.mouse_pos
        pygame.draw.circle(self.screen, BLACK, (mx, my), 6, 1)
        pygame.draw.line(self.screen, BLACK, (mx - 10, my), (mx + 10, my), 1)
        pygame.draw.line(self.screen, BLACK, (mx, my - 10), (mx, my + 10), 1)

        # layer 6: HUD
        idle = time.time() - self.last_move_time
        mode_names = {
            "spiral": "Spiral",
            "brownian": "Brownian",
            "circle": "Circle",
        }
        mode_label = mode_names.get(self.auto_type, "--")
        grad_str = ""
        if self.gradient_active:
            pct = 100 * (1 - self.gradient_remaining / self.GRADIENT_LENGTH)
            grad_str = f"  |  Gradient: {pct:.0f}%"
        move_dur = time.time() - self.continuous_move_start if self.continuous_move_start > 0 else 0
        lines = [
            f"Drawing: {'ON' if self.drawing else 'OFF'}  |  "
            f"Auto: {'ON' if self.auto_drawing else 'OFF'}"
            f" ({mode_label})  |  "
            f"FPS: {int(self.clock.get_fps())}{grad_str}",
            f"Idle: {idle:.1f}s / {self.idle_threshold:.1f}s  |  "
            f"Move: {move_dur:.1f}s  |  777: {'READY' if move_dur >= 10 and not self.checked_777 else '--'}  |  "
            f"Port: {PORT}",
            f"Brush: {self.brush_color}  |  Auto: {self.auto_color}  |  "
            f"[C]lear  [P]en  [O]Gradient  [Space]Auto  [Esc]Quit",
            f"Spiral(blue)  Brownian(green)  Circle(orange)",
        ]
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, BLACK)
            self.screen.blit(surf, (12, 12 + i * 22))

        pygame.display.flip()

    # ═══════════════════════════════════════════════════════
    #  MAIN LOOP
    # ═══════════════════════════════════════════════════════
    def run(self):
        print("=" * 55)
        print("  DrawingBoard v1.2")
        print(f"  Window: {WINDOW_WIDTH}x{WINDOW_HEIGHT} @ {FPS} FPS")
        print(f"  TCP Server: port {PORT}")
        print("  Modes: Archimedean spiral | Brownian | Circle")
        print("  Features: Gradient brush (O key) | 777 mechanism")
        print("  Controls:")
        print("    Left-drag   - free draw")
        print("    Idle 10-39s - auto draw from line endpoint")
        print("    C key       - clear canvas")
        print("    P key       - random brush color")
        print("    O key       - gradient to random color (10 cm)")
        print("    Space       - toggle auto-draw")
        print("    Esc         - quit")
        print("=" * 55)

        while self.running:
            self._handle_events()
            self._update()
            self._render()
            self.clock.tick(FPS)

        self._cleanup()

    def _cleanup(self):
        self.server_running = False
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    app = DrawingBoard()
    app.run()
