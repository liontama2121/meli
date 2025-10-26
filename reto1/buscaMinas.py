# -*- coding: utf-8 -*-
"""
Buscaminas Mercado Libre – versión ventana normal (sin pantalla completa)
Autor: Juan Camilo Molina
"""

import pygame, random, time

# Colores
MELI_YELLOW = (255,230,0)
MELI_BLUE   = (0,47,108)
WHITE       = (255,255,255)
GRAY_1      = (240,242,245)
GRAY_2      = (210,214,219)
RED_ALERT   = (255,68,68)
GREEN_OK    = (46,204,113)
INK         = (15,17,21)
FONT_NAME = None

LEVELS = {
    "Fácil": {"rows": 12, "cols": 12, "mines": 20},
    "Medio": {"rows": 16, "cols": 20, "mines": 50},
    "Difícil": {"rows": 20, "cols": 24, "mines": 80}
}

UI_BAR_H = 80
MARGIN = 10

# ---- Lógica básica de minas ----
def contar_minas_vecinas(tablero):
    filas, columnas = len(tablero), len(tablero[0])
    res = [[0]*columnas for _ in range(filas)]
    direcciones = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    for f in range(filas):
        for c in range(columnas):
            if tablero[f][c] == 1:
                res[f][c] = 9
            else:
                res[f][c] = sum(
                    tablero[f+af][c+ac] == 1
                    for af,ac in direcciones
                    if 0 <= f+af < filas and 0 <= c+ac < columnas
                )
    return res

class Cell:
    def __init__(self, r, c):
        self.r, self.c = r, c
        self.has_mine = False
        self.revealed = False
        self.flagged = False
        self.count = 0

class Board:
    def __init__(self, rows, cols, mines):
        self.rows, self.cols, self.mines = rows, cols, mines
        self.grid = [[Cell(r,c) for c in range(cols)] for r in range(rows)]
        self._place_mines()
        self._counts()
        self.revealed_count = 0
        self.flags = 0
        self.game_over = False
        self.win = False

    def _place_mines(self):
        for (r,c) in random.sample([(r,c) for r in range(self.rows) for c in range(self.cols)], self.mines):
            self.grid[r][c].has_mine = True

    def _counts(self):
        base = [[1 if self.grid[r][c].has_mine else 0 for c in range(self.cols)] for r in range(self.rows)]
        nums = contar_minas_vecinas(base)
        for r in range(self.rows):
            for c in range(self.cols):
                self.grid[r][c].count = nums[r][c]

    def in_bounds(self, r, c): return 0 <= r < self.rows and 0 <= c < self.cols

    def reveal(self, r, c):
        if not self.in_bounds(r,c): return
        cell = self.grid[r][c]
        if cell.revealed or cell.flagged: return
        cell.revealed = True
        self.revealed_count += 1
        if cell.has_mine:
            self.game_over = True
            return
        if cell.count == 0:
            for dr in (-1,0,1):
                for dc in (-1,0,1):
                    if dr or dc:
                        self.reveal(r+dr, c+dc)
        if self.revealed_count == self.rows * self.cols - self.mines:
            self.win = True

    def toggle_flag(self, r, c):
        if not self.in_bounds(r,c): return
        cell = self.grid[r][c]
        if cell.revealed: return
        cell.flagged = not cell.flagged
        self.flags += 1 if cell.flagged else -1

    def reveal_all(self):
        for fila in self.grid:
            for cell in fila:
                cell.revealed = True

# ---- UI ----
def compute_cell_size(rows, cols, max_w=1200, max_h=720):
    return int(max(20, min(40, (max_w-40)//cols, (max_h-160)//rows)))

class Button:
    def __init__(self, rect, text, font):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.hover = False

    def draw(self, surface):
        color = GRAY_1 if self.hover else WHITE
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, MELI_BLUE, self.rect, 3, border_radius=10)
        txt = self.font.render(self.text, True, MELI_BLUE)
        surface.blit(txt, (self.rect.x + (self.rect.w - txt.get_width())//2, self.rect.y + (self.rect.h - txt.get_height())//2))

    def update_hover(self, mx, my): self.hover = self.rect.collidepoint(mx, my)
    def clicked(self, mx, my): return self.rect.collidepoint(mx, my)

# ---- Juego ----
class MeliMines:
    def __init__(self):
        pygame.init()
        self.screen_w, self.screen_h = 1200, 720
        pygame.display.set_caption("Buscaminas Mercado Libre")
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont(FONT_NAME, 26, bold=True)
        self.font_big = pygame.font.SysFont(FONT_NAME, 40, bold=True)
        self.font_huge = pygame.font.SysFont(FONT_NAME, 60, bold=True)

        self.state = "menu"
        self.board = None
        self.level_name = None
        self.cell_size = 28
        self.offset_x = 0
        self.offset_y = UI_BAR_H + 10
        self.start_time = 0
        self.elapsed = 0

        # Botones
        self.btn_restart = Button((self.screen_w - 240, 20, 100, 40), "Reiniciar", self.font)
        self.btn_exit = Button((self.screen_w - 120, 20, 80, 40), "Salir", self.font)

    def run(self):
        running = True
        while running:
            mx, my = pygame.mouse.get_pos()
            self.btn_restart.update_hover(mx, my)
            self.btn_exit.update_hover(mx, my)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN:
                    self.key(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN:
                    self.mouse(e)
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()

    def key(self, k):
        if self.state == "menu":
            if k == pygame.K_1: self.start_level("Fácil")
            elif k == pygame.K_2: self.start_level("Medio")
            elif k == pygame.K_3: self.start_level("Difícil")

    def mouse(self, e):
        mx, my = e.pos
        if self.btn_exit.clicked(mx,my): pygame.quit(); exit()
        if self.btn_restart.clicked(mx,my) and self.level_name: self.start_level(self.level_name); return
        if self.state != "playing" or not self.board: return
        r,c = self.pixel_to_cell(mx,my)
        if r is None: return
        if e.button == 1:
            self.board.reveal(r,c)
            if self.board.game_over:
                self.board.reveal_all()
                self.state = "over"
            elif self.board.win:
                self.state = "win"
        elif e.button == 3:
            self.board.toggle_flag(r,c)

    def update(self):
        if self.state == "playing": self.elapsed = time.time() - self.start_time

    def start_level(self, name):
        cfg = LEVELS[name]
        self.level_name = name
        self.board = Board(cfg["rows"], cfg["cols"], cfg["mines"])
        self.cell_size = compute_cell_size(cfg["rows"], cfg["cols"], self.screen_w, self.screen_h)
        board_w = self.board.cols * self.cell_size
        self.offset_x = (self.screen_w - board_w)//2
        self.start_time = time.time()
        self.state = "playing"

    def pixel_to_cell(self, x,y):
        bx, by = x - self.offset_x, y - self.offset_y
        if not self.board or bx<0 or by<0: return None, None
        c, r = bx//self.cell_size, by//self.cell_size
        if r>=self.board.rows or c>=self.board.cols: return None, None
        return int(r), int(c)

    def draw(self):
        self.screen.fill(MELI_YELLOW)
        pygame.draw.rect(self.screen, MELI_BLUE, (0,0,self.screen_w,UI_BAR_H))
        title = self.font_big.render("Buscaminas Mercado Libre", True, WHITE)
        self.screen.blit(title, (self.screen_w//2 - title.get_width()//2, 20))
        self.btn_restart.draw(self.screen)
        self.btn_exit.draw(self.screen)
        if self.state == "menu":
            t1 = self.font_huge.render("Seleccione nivel", True, MELI_BLUE)
            t2 = self.font.render("1) Fácil   2) Medio   3) Difícil", True, MELI_BLUE)
            self.screen.blit(t1, (self.screen_w//2 - t1.get_width()//2, 250))
            self.screen.blit(t2, (self.screen_w//2 - t2.get_width()//2, 330))
        else:
            self.draw_board()
            if self.state == "over": self.banner("¡BOOM!", RED_ALERT)
            elif self.state == "win": self.banner("¡GANÓ!", GREEN_OK)

    def draw_board(self):
        if not self.board: return
        b, cs, ox, oy = self.board, self.cell_size, self.offset_x, self.offset_y
        pygame.draw.rect(self.screen, WHITE, (ox-6,oy-6,b.cols*cs+12,b.rows*cs+12), border_radius=14)
        for r in range(b.rows):
            for c in range(b.cols):
                x,y = ox+c*cs, oy+r*cs
                cell = b.grid[r][c]
                color = WHITE if cell.revealed else GRAY_2
                pygame.draw.rect(self.screen, color, (x+2,y+2,cs-4,cs-4), border_radius=8)
                if cell.revealed:
                    if cell.has_mine and self.state == "over":
                        txt = self.font.render("9", True, MELI_BLUE)
                        self.screen.blit(txt, (x+(cs-txt.get_width())//2, y+(cs-txt.get_height())//2))
                    elif cell.count > 0:
                        txt = self.font.render(str(cell.count), True, MELI_BLUE)
                        self.screen.blit(txt, (x+(cs-txt.get_width())//2, y+(cs-txt.get_height())//2))
                elif cell.flagged:
                    pygame.draw.polygon(self.screen, MELI_BLUE, [(x+cs*0.3,y+cs*0.3),(x+cs*0.7,y+cs*0.4),(x+cs*0.3,y+cs*0.5)])

    def banner(self,text,color):
        surf = self.font_huge.render(text,True,WHITE)
        bx, by = (self.screen_w-surf.get_width()-80)//2, (self.screen_h-surf.get_height()-40)//2
        pygame.draw.rect(self.screen,color,(bx,by,surf.get_width()+80,surf.get_height()+40),border_radius=20)
        self.screen.blit(surf,(bx+40,by+20))

if __name__ == "__main__":
    MeliMines().run()
