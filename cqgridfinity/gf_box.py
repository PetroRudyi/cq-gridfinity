#! /usr/bin/env python3
#
# Copyright (C) 2023  Michael Gale
# This file is part of the cq-gridfinity python module.
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Gridfinity Boxes

import math

import cadquery as cq
from cqkit import HasZCoordinateSelector, VerticalEdgeSelector, FlatEdgeSelector
from cqkit.cq_helpers import rounded_rect_sketch, composite_from_pts
from cqgridfinity import *


class GridfinityBox(GridfinityObject):
    """Gridfinity Box

    This class represents a Gridfinity compatible box module. As a minimum,
    this class is initialized with basic 3D unit dimensions for length,
    width, and height.  length and width are multiples of 42 mm Gridfinity
    intervals and height represents multiples of 7 mm.

    Many box features can be enabled with attributes provided either as
    keywords or direct dotted access.  These attributes include:
    - solid :   renders the box without an interior, i.e. a solid block. This
                is useful for making custom Gridfinity modules by subtracting
                out shapes from the solid interior. Normally, the box is
                rendered solid up to its maximum size; however, the
                solid_ratio attribute can specify a solid fill of between
                0.0 to 1.0, i.e. 0 to 100% fill.
    - holes : adds bottom mounting holes for magnets or screws
    - scoops : adds a radiused bottom edge to the interior to help fetch
               parts from the box
    - labels : adds a flat flange along each compartment for adding a label
    - no_lip : removes the contoured lip on the top module used for stacking
    - length_div, width_div : subdivides the box into sub-compartments in
                 length and/or width.
    - lite_style : render box as an economical shell without elevated floor
    - unsupported_holes : render bottom holes as 3D printer friendly versions
                          which can be printed without supports
    - label_width : width of top label ledge face overhang
    - label_height : height of label ledge overhang
    - scoop_rad : radius of the bottom scoop feature
    - scoop_axis : direction of scoops: "length" (default, along front wall),
                   "width" (along side wall), or "both"
    - wall_th : wall thickness
    - hole_diam : magnet/counterbore bolt hole diameter

    """

    def __init__(self, length_u, width_u, height_u, **kwargs):
        super().__init__()
        self.length_u = length_u
        self.width_u = width_u
        self.height_u = height_u
        self.length_div = 0
        self.width_div = 0
        self.length_div_ratio = None
        self.width_div_ratio = None
        self.scoops = False
        self.labels = False
        self.solid = False
        self.holes = False
        self.no_lip = False
        self.solid_ratio = 1.0
        self.lite_style = False
        self.unsupported_holes = False
        self.label_width = 12  # width of the label strip
        self.label_height = 10  # thickness of label overhang
        self.label_lip_height = 0.8  # thickness of label vertical lip
        self.scoop_rad = 14  # radius of optional interior scoops
        self.scoop_axis = "length"  # "length", "width", or "both"
        self.fillet_interior = True
        self.wall_th = GR_WALL
        self.hole_diam = GR_HOLE_D  # magnet/bolt hole diameter
        for k, v in kwargs.items():
            if k in self.__dict__:
                self.__dict__[k] = v
        self._int_shell = None
        self._ext_shell = None

    def __str__(self):
        s = []
        s.append(
            "Gridfinity Box %dU x %dU x %dU (%.2f x %.2f x %.2f mm)"
            % (
                self.length_u,
                self.width_u,
                self.height_u,
                self.length - GR_TOL,
                self.width - GR_TOL,
                self.height,
            )
        )
        sl = "no mating top lip" if self.no_lip else "with mating top lip"
        ss = "Lite style box  " if self.lite_style else ""
        s.append("  %sWall thickness: %.2f mm  %s" % (ss, self.wall_th, sl))
        s.append(
            "  Floor height  : %.2f mm  Inside height: %.2f mm  Top reference height: %.2f mm"
            % (self.floor_h + GR_BASE_HEIGHT, self.int_height, self.top_ref_height)
        )
        if self.solid:
            s.append("  Solid filled box with fill ratio %.2f" % (self.solid_ratio))
        if self.holes:
            s.append("  Bottom mounting holes with %.2f mm diameter" % (self.hole_diam))
            if self.unsupported_holes:
                s.append("  Holes are 3D printer friendly and can be unsupported")
        if self.scoops:
            axis_label = {"length": "Lengthwise", "width": "Widthwise", "both": "Both axes"}
            s.append("  %s scoops with %.2f mm radius" % (axis_label.get(self.scoop_axis, "Lengthwise"), self.scoop_rad))
        if self.labels:
            s.append(
                "  Lengthwise label shelf %.2f mm wide with %.2f mm overhang"
                % (self.label_width, self.label_height)
            )
        if self.length_div:
            xl = (self.inner_l - GR_DIV_WALL * (self.length_div)) / (
                    self.length_div + 1
            )
            ratio_str = ""
            if self.length_div_ratio is not None:
                ratio_str = " ratio %s" % self.length_div_ratio
            s.append(
                "  %dx lengthwise divisions%s"
                % (self.length_div, ratio_str)
            )
        if self.width_div:
            yl = (self.inner_w - GR_DIV_WALL * (self.width_div)) / (self.width_div + 1)
            ratio_str = ""
            if self.width_div_ratio is not None:
                ratio_str = " ratio %s" % self.width_div_ratio
            s.append(
                "  %dx widthwise divisions%s"
                % (self.width_div, ratio_str)
            )
        s.append("  Auto filename: %s" % (self.filename()))
        return "\n".join(s)

    def render(self):
        """Returns a CadQuery Workplane object representing this Gridfinity box."""
        self._int_shell = None
        if self.lite_style:
            # just force the dividers to the desired quantity in both dimensions
            # rather than raise a exception
            if self.length_div > self.length_u - 1:
                self.length_div = self.length_u - 1
            if self.width_div > self.width_u - 1:
                self.width_div = self.width_u - 1
            if self.solid:
                raise ValueError(
                    "Cannot select both solid and lite box styles together"
                )
            if self.holes:
                raise ValueError(
                    "Cannot select both holes and lite box styles together"
                )
            if self.wall_th > 1.5:
                raise ValueError(
                    "Wall thickness cannot exceed 1.5 mm for lite box style"
                )
        if self.wall_th > 2.5:
            raise ValueError("Wall thickness cannot exceed 2.5 mm")
        if self.wall_th < 0.5:
            raise ValueError("Wall thickness must be at least 0.5 mm")
        if self.length_div_ratio is not None:
            if len(self.length_div_ratio) != self.length_div + 1:
                raise ValueError(
                    "length_div_ratio must have %d elements (length_div + 1), got %d"
                    % (self.length_div + 1, len(self.length_div_ratio))
                )
            if any(v <= 0 for v in self.length_div_ratio):
                raise ValueError("All values in length_div_ratio must be positive")
        if self.width_div_ratio is not None:
            if len(self.width_div_ratio) != self.width_div + 1:
                raise ValueError(
                    "width_div_ratio must have %d elements (width_div + 1), got %d"
                    % (self.width_div + 1, len(self.width_div_ratio))
                )
            if any(v <= 0 for v in self.width_div_ratio):
                raise ValueError("All values in width_div_ratio must be positive")
        r = self.render_shell()

        rd = self.render_dividers()

        rs = self.render_scoops()
        rl = self.render_labels()
        for e in (rd, rl, rs):
            if e is not None:
                r = r.union(e)
        # if not self.solid and self.fillet_interior:
        #     heights = [GR_FLOOR]
        #     if self.labels:
        #         heights.append(self.safe_label_height(backwall=True, from_bottom=True))
        #         heights.append(self.safe_label_height(backwall=False, from_bottom=True))
        #     bs = (
        #         HasZCoordinateSelector(heights, min_points=1, tolerance=0.5)
        #         + VerticalEdgeSelector(">5")
        #         - HasZCoordinateSelector("<%.2f" % (self.floor_h))
        #     )
        #     if self.lite_style and self.scoops:
        #         bs = bs - HasZCoordinateSelector("<=%.2f" % (self.floor_h))
        #         bs = bs - VerticalEdgeSelector()
        #     r = self.safe_fillet(r, bs, self.safe_fillet_rad)
        #
        #     if self.lite_style and not self.has_dividers:
        #         bs = FlatEdgeSelector(self.floor_h)
        #         if self.wall_th < 1.2:
        #             r = self.safe_fillet(r, bs, 0.5)
        #         elif self.wall_th < 1.5:
        #             r = self.safe_fillet(r, bs, 0.25)
        #
        #     if not self.labels and self.has_dividers:
        #         bs = VerticalEdgeSelector(
        #             GR_TOPSIDE_H, tolerance=0.05
        #         ) & HasZCoordinateSelector(GRHU * self.height_u - GR_BASE_HEIGHT)
        #         r = self.safe_fillet(r, bs, GR_TOPSIDE_H - EPS)
        #
        if self.holes:
            r = self.render_holes(r)
        r = r.translate((-self.half_l, -self.half_w, GR_BASE_HEIGHT))
        if self.unsupported_holes:
            r = self.render_hole_fillers(r)
        return r

    @property
    def top_ref_height(self):
        """The height of the top surface of a solid box or the floor
        height of an empty box."""
        if self.solid:
            return self.max_height * self.solid_ratio + GR_BOT_H
        if self.lite_style:
            return self.floor_h
        return GR_BOT_H

    @property
    def bin_height(self):
        return self.height - GR_BASE_HEIGHT

    def safe_label_height(self, backwall=False, from_bottom=False):
        lw = self.label_width
        if backwall:
            lw += self.lip_width
        lh = self.label_height * (lw / self.label_width)
        yl = self.max_height - self.label_height + self.wall_th
        if backwall:
            yl -= self.lip_width
        if yl < 0:
            lh = self.max_height - 1.5 * GR_FILLET - 0.1
        elif yl < 1.5 * GR_FILLET:
            lh -= 1.5 * GR_FILLET - yl + 0.1
        if from_bottom:
            ws = math.sin(math.atan2(self.label_height, self.label_width))
            if backwall:
                lh = self.max_height + GR_FLOOR - lh + ws * self.wall_th
            else:
                lh = self.max_height + GR_FLOOR - lh + ws * GR_DIV_WALL
        return lh

    @property
    def has_dividers(self):
        return self.length_div > 0 or self.width_div > 0

    @property
    def interior_solid(self):
        if self._int_shell is not None:
            return self._int_shell
        self._int_shell = self.render_interior()
        return self._int_shell

    def render_interior(self, force_solid=False):
        """Renders the interior cutting solid of the box."""
        wall_u = self.wall_th - GR_WALL
        wall_h = self.int_height + wall_u
        # print('wall_u', wall_u)
        under_h = ((GR_UNDER_H - wall_u) * SQRT2, 45)
        profile = GR_NO_PROFILE if self.no_lip else [under_h, *GR_LIP_PROFILE[1:]]
        # print('profile for self.no_lip==', self.no_lip)
        #
        print('self.height', self.height)
        print('GR_LIP_H', GR_LIP_H)
        print('GR_BOT_H', GR_BOT_H)
        print('self.wall_th', self.wall_th)
        print('self.int_height', self.int_height)
        # print('self.max_height', self.max_height)
        print('profile 1 ', profile)
        profile = [wall_h + GR_TOL + 0.336, *profile]
        if self.int_height < 0:
            profile = [self.height - GR_BOT_H + GR_TOL + 0.336, (self.wall_th * SQRT2, -45), ]

        print('profile 2 ', profile)
        rci = self.extrude_profile(
            rounded_rect_sketch(*self.inner_dim, self.inner_rad), profile
        )

        rci = rci.translate((*self.half_dim, self.floor_h - GR_BASE_CLR - 0.336))

        if self.solid or force_solid:
            hs = self.max_height * self.solid_ratio
            ri = rounded_rect_sketch(*self.inner_dim, self.inner_rad)
            rf = cq.Workplane("XY").placeSketch(ri).extrude(hs)
            rf = rf.translate((*self.half_dim, self.floor_h))
            rci = rci.cut(rf)

        if self.scoops and not self.no_lip:
            cut_h = self.floor_h + self.max_height
            if self.scoop_axis in ("length", "both"):
                rf = (
                    cq.Workplane("XY")
                    .rect(self.inner_l, 2 * self.under_h)
                    .extrude(cut_h)
                    .translate((self.half_l, -self.half_in, 0))
                )
                rci = rci.cut(rf)
            if self.scoop_axis in ("width", "both"):
                rf = (
                    cq.Workplane("XY")
                    .rect(2 * self.under_h, self.inner_w)
                    .extrude(cut_h)
                    .translate((-self.half_in, self.half_w, 0))
                )
                rci = rci.cut(rf)
        if self.lite_style:
            r = composite_from_pts(self.base_interior(), self.grid_centres)
            rci = rci.union(r)
        return rci

    def solid_shell(self):
        """Returns a completely solid box object useful for intersecting with other solids."""
        if self._ext_shell is not None:
            return self._ext_shell
        r = self.render_shell(as_solid=True)
        self._ext_shell = r.cut(self.render_interior(force_solid=True))
        return self._ext_shell

    def mask_with_obj(self, obj):
        """Intersects a solid object with this box."""
        return obj.intersect(self.solid_shell())

    def base_interior(self):
        profile = [GR_BASE_HEIGHT, *GR_BOX_PROFILE]
        zo = GR_BASE_HEIGHT + GR_BASE_CLR
        if self.int_height < 0:
            h = self.bin_height - GR_BASE_HEIGHT
            profile = [h, *profile]
            zo += h
        r = self.extrude_profile(
            rounded_rect_sketch(GRU - GR_TOL, GRU - GR_TOL, self.outer_rad),
            profile,
        )
        rx = r.faces("<Z").shell(-self.wall_th)
        r = r.cut(rx).mirror(mirrorPlane="XY").translate((0, 0, zo))
        return r

    def render_shell(self, as_solid=False):
        """Renders the box shell without any added features."""
        r = self.extrude_profile(
            rounded_rect_sketch(GRU - GR_TOL, GRU - GR_TOL, self.outer_rad + GR_BASE_CLR), GR_BOX_PROFILE
        )
        r = r.translate((0, 0, -GR_BASE_CLR))
        r = r.mirror(mirrorPlane="XY")
        r = composite_from_pts(r, self.grid_centres)
        rs = rounded_rect_sketch(*self.outer_dim, self.outer_rad)  # < WTF IS THAT???
        rw = (
            cq.Workplane("XY")
            .placeSketch(rs)
            .extrude(self.bin_height)
            .translate((*self.half_dim, GR_BASE_CLR))
        )
        rc = (
            cq.Workplane("XY")
            .placeSketch(rs)
            .extrude(-GR_BASE_HEIGHT - 1)
            .translate((*self.half_dim, 0.5))
        )
        rc = rc.intersect(r).union(rw)
        if not as_solid:
            return rc.cut(self.interior_solid)
        return rc

    def _div_positions(self, count, inner_dim, unit_count, ratios_attr):
        """Returns list of positions for dividers along a dimension.
        For lite_style, positions are snapped to cell boundaries."""
        ratios = ratios_attr or [1] * (count + 1)
        total = sum(ratios)
        cumulative = 0
        positions = []
        for i in range(count):
            cumulative += ratios[i]
            raw = cumulative / total * inner_dim
            if self.lite_style:
                cell_size = inner_dim / unit_count
                raw = round(raw / cell_size) * cell_size
                raw = max(cell_size, min(raw, inner_dim - cell_size))
            positions.append(raw - self.half_in)
        return positions

    def _length_div_positions(self):
        return self._div_positions(
            self.length_div, self.inner_l, self.length_u, self.length_div_ratio
        )

    def _width_div_positions(self):
        return self._div_positions(
            self.width_div, self.inner_w, self.width_u, self.width_div_ratio
        )

    @property
    def _dividers_allowed(self):
        """Dividers are allowed for non-solid boxes,
        or solid boxes with solid_ratio < 0.95 (partial fill)."""
        if not self.solid:
            return True
        return self.solid_ratio < 0.95

    @property
    def _divider_height(self):
        """Height of divider walls — full interior height from the actual floor."""
        return self.max_height + GR_BASE_CLR + 0.336

    @property
    def _divider_floor(self):
        """Z-offset for the bottom of divider walls.
        Matches the actual interior floor from render_interior."""
        return self.floor_h - GR_BASE_CLR - 0.336

    def render_dividers(self):
        r = None
        if not self._dividers_allowed:
            return r

        div_h = self._divider_height
        div_floor = self._divider_floor

        if self.length_div > 0:
            wall_w = (
                cq.Workplane("XY")
                .rect(GR_DIV_WALL, self.outer_w)
                .extrude(div_h)
                .translate((0, 0, div_floor))
            )
            x_positions = self._length_div_positions()
            pts = [(xp, self.half_w) for xp in x_positions]
            r = composite_from_pts(wall_w, pts)

        if self.width_div > 0:
            wall_l = (
                cq.Workplane("XY")
                .rect(self.outer_l, GR_DIV_WALL)
                .extrude(div_h)
                .translate((0, 0, div_floor))
            )
            y_positions = self._width_div_positions()
            pts = [(self.half_l, yp) for yp in y_positions]
            rw = composite_from_pts(wall_l, pts)
            if r is not None:
                r = r.union(rw)
            else:
                r = rw
        # clip dividers to the shell shape to prevent protrusion at rounded corners
        if r is not None:
            r = r.intersect(self.render_shell(as_solid=True))
        return r

    def _render_length_scoops(self, srad, zo):
        """Scoops along the front wall (Y-axis), extruded in the length (X) direction."""
        rs = cq.Sketch().rect(srad, srad).vertices(">X and >Y").circle(srad, mode="s")
        rsc = cq.Workplane("YZ").placeSketch(rs).extrude(self.inner_l)
        rsc = rsc.translate((0, 0, srad / 2 + GR_FLOOR - GR_BASE_CLR - 0.336))
        yo = -self.half_in + srad / 2
        if not self.no_lip:
            yo += self.under_h
        rs = rsc.translate((-self.half_in, yo, zo))
        r = rs.intersect(self.interior_solid)
        if self.width_div > 0:
            y_positions = self._width_div_positions()
            pts = [(-self.half_in, yp) for yp in y_positions]
            rs = composite_from_pts(rsc, pts)
            r = r.union(rs.translate((0, GR_DIV_WALL / 2 + srad / 2, zo)))
            r = r.intersect(self.render_shell(as_solid=True))
        return r

    def _render_width_scoops(self, srad, zo):
        """Scoops along the side wall (X-axis), extruded in the width (Y) direction."""
        rs = cq.Sketch().rect(srad, srad).vertices(">X and >Y").circle(srad, mode="s")
        # XZ plane normal is -Y, so extrude goes in -Y; offset by inner_w to place correctly
        rsc = cq.Workplane("XZ").placeSketch(rs).extrude(self.inner_w)
        rsc = rsc.translate((0, self.inner_w, srad / 2 + GR_FLOOR - GR_BASE_CLR - 0.336))
        xo = -self.half_in + srad / 2
        if not self.no_lip:
            xo += self.under_h
        rs = rsc.translate((xo, -self.half_in, zo))
        r = rs.intersect(self.interior_solid)
        if self.length_div > 0:
            x_positions = self._length_div_positions()
            pts = [(xp, -self.half_in) for xp in x_positions]
            rs = composite_from_pts(rsc, pts)
            r = r.union(rs.translate((GR_DIV_WALL / 2 + srad / 2, 0, zo)))
            r = r.intersect(self.render_shell(as_solid=True))
        return r

    def render_scoops(self):
        if not self.scoops:
            return None
        if self.solid and self.solid_ratio >= 0.95:
            return None
        srad = min(self.scoop_rad, self.int_height - 0.1)
        if srad <= 0:
            return None
        zo = -GR_BOT_H + self.wall_th if self.lite_style else 0
        r = None
        if self.scoop_axis in ("length", "both"):
            r = self._render_length_scoops(srad, zo)
        if self.scoop_axis in ("width", "both"):
            rw = self._render_width_scoops(srad, zo)
            r = r.union(rw) if r is not None else rw
        return r

    def render_labels(self):
        if not self.labels or self.solid:
            return None
        # back wall label flange with compensated width and height
        lw = self.label_width + self.lip_width
        rs = (
            cq.Sketch()
            .segment((0, 0), (lw, 0))
            .segment((lw, -self.safe_label_height(backwall=True)))
            .segment((0, -self.label_lip_height))
            .close()
            .assemble()
            .vertices("<X")
            .vertices("<Y")
            .fillet(self.label_lip_height / 2)
        )
        rsc = cq.Workplane("YZ").placeSketch(rs).extrude(self.inner_l)
        yo = -lw + self.outer_w / 2 + self.half_w + self.wall_th / 4
        rs = rsc.translate((-self.half_in, yo, self.floor_h + self.max_height))
        # intersect to prevent solids sticking out of rounded corners
        r = rs.intersect(self.interior_solid)
        if self.width_div > 0:
            # add label flanges along each dividing wall
            rs = (
                cq.Sketch()
                .segment((0, 0), (self.label_width, 0))
                .segment((self.label_width, -self.safe_label_height(backwall=False)))
                .segment((0, -self.label_lip_height))
                .close()
                .assemble()
                .vertices("<X")
                .vertices("<Y")
                .fillet(self.label_lip_height / 2)
            )
            rsc = cq.Workplane("YZ").placeSketch(rs).extrude(self.inner_l)
            rsc = rsc.translate((0, -self.label_width, self.floor_h + self.max_height))
            y_positions = self._width_div_positions()
            pts = [
                (-self.half_in, yp + GR_DIV_WALL / 2)
                for yp in y_positions
            ]
            r = r.union(composite_from_pts(rsc, pts))
        return r

    def render_holes(self, obj):
        if not self.holes:
            return obj
        h = GR_HOLE_H
        if self.unsupported_holes:
            h += GR_HOLE_SLICE
        return (
            obj.faces("<Z")
            .workplane()
            .pushPoints(self.hole_centres)
            .cboreHole(GR_BOLT_D, self.hole_diam, h, depth=GR_BOLT_H)
        )

    def render_hole_fillers(self, obj):
        rc = (
            cq.Workplane("XY")
            .rect(self.hole_diam / 2, self.hole_diam)
            .extrude(GR_HOLE_SLICE)
        )
        xo = self.hole_diam / 2
        filler_z = GR_HOLE_H + GR_BASE_CLR
        rs = composite_from_pts(rc, [(-xo, 0, filler_z), (xo, 0, filler_z)])
        rs = composite_from_pts(rs, self.hole_centres)
        return obj.union(rs.translate((-self.half_l, self.half_w, 0)))


class GridfinitySolidBox(GridfinityBox):
    """Convenience class to represent a solid Gridfinity box."""

    def __init__(self, length_u, width_u, height_u, **kwargs):
        super().__init__(length_u, width_u, height_u, **kwargs, solid=True)
