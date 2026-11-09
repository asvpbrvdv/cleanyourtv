package com.gathin.tvhome;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.LayerDrawable;

import java.util.Locale;

/**
 * Shared pieces of the dot-matrix design (docs/designs/dot-matrix): the three modes, their colours, the NYC
 * Subway line colours colour mode uses as identifiers, the dot-grid background and the round bullets.
 * The XML resources read the colours through theme attributes (Theme.TvHome.Dark, .Light, .Color); code that
 * draws by itself asks {@link #palette(int)}.
 */
final class DotMatrix {

    static final int DARK = 0, LIGHT = 1, COLOR = 2;

    // NYC Subway line colours.
    static final int RED = 0xFFEE352E, GREEN = 0xFF00933C, BLUE = 0xFF0039A6, ORANGE = 0xFFFF6319,
            YELLOW = 0xFFFCCC0A, PURPLE = 0xFFB933AD, LIME = 0xFF6CBE45, BROWN = 0xFF996633, GREY = 0xFFA7A9AC;
    /** Dock slots 1 to 4. */
    static final int[] DOCK_LINES = {RED, GREEN, BLUE, ORANGE};
    /** Grid apps A, B, C..., cycling. */
    static final int[] GRID_LINES = {YELLOW, PURPLE, LIME, BROWN, GREY, BLUE, GREEN, ORANGE};
    /** Inputs rows, in order, cycling. */
    static final int[] INPUT_LINES = {RED, GREEN, BLUE, ORANGE, YELLOW};
    /** Top-bar segments. */
    static final int INPUTS_LINE = ORANGE, WIFI_LINE = BLUE, SETTINGS_LINE = GREY, MODE_LINE = PURPLE;

    /** The red of dark and light mode. */
    static final int ACCENT = 0xFFD71921;

    private DotMatrix() {
    }

    /** "dark", "light" or "color" (any case, "colour" too) to a mode; anything else to {@code fallback}. */
    static int parseMode(String value, int fallback) {
        if (value == null) return fallback;
        switch (value.trim().toLowerCase(Locale.ROOT)) {
            case "dark":
                return DARK;
            case "light":
                return LIGHT;
            case "color":
            case "colour":
                return COLOR;
            default:
                return fallback;
        }
    }

    static String modeName(int mode) {
        return mode == LIGHT ? "light" : mode == COLOR ? "color" : "dark";
    }

    static int next(int mode) {
        return (mode + 1) % 3;
    }

    /** Applies the mode's colours to this context's theme; call before inflating anything. */
    static void applyMode(Context ctx, int mode) {
        ctx.getTheme().applyStyle(mode == LIGHT ? R.style.DotMatrix_Light : mode == COLOR ? R.style.DotMatrix_Color
                : R.style.DotMatrix_Dark, true);
    }

    static int label(int mode) {
        return mode == LIGHT ? R.string.mode_light : mode == COLOR ? R.string.mode_color : R.string.mode_dark;
    }

    /** One mode's colours, for what code draws itself. */
    static final class Palette {
        final int mode;
        final int background, ink, onInk, ink30, gridDot, tileOutline;
        /** The accent of everything without a line colour of its own (red; colour mode's own red). */
        final int accent;
        /** Unfocused tiles: brightness and contrast after taking the colour out. */
        final float greyBrightness, greyContrast;

        Palette(int mode) {
            this.mode = mode;
            boolean light = mode == LIGHT;
            background = light ? 0xFFECEBE6 : 0xFF000000;
            ink = light ? 0xFF111111 : 0xFFF2F2F2;
            onInk = light ? 0xFFF2F2F2 : 0xFF000000;
            ink30 = (ink & 0x00FFFFFF) | 0x4D000000;
            gridDot = light ? 0x1A000000 : 0x13FFFFFF;
            tileOutline = light ? 0x1F000000 : 0x24FFFFFF;
            accent = mode == COLOR ? RED : ACCENT;
            greyBrightness = light ? 1f : 0.75f;
            greyContrast = light ? 0.92f : 1f;
        }

        boolean colour() {
            return mode == COLOR;
        }

        /** A line colour in colour mode, the accent otherwise. */
        int line(int lineColour) {
            return mode == COLOR ? lineColour : accent;
        }
    }

    static Palette palette(int mode) {
        return new Palette(mode);
    }

    /** Black text on the yellow and grey bullets, white on the rest, as on the subway. */
    static int bulletText(int lineColour) {
        return lineColour == YELLOW || lineColour == GREY ? 0xFF000000 : 0xFFFFFFFF;
    }

    /** {@code focused} on a focused (or selected) view, {@code normal} otherwise. */
    static ColorStateList focusColours(int focused, int normal) {
        return new ColorStateList(
                new int[][]{{android.R.attr.state_focused}, {android.R.attr.state_selected}, {}},
                new int[]{focused, focused, normal});
    }

    /** The background colour with a faint dot grid: 1.1dp dots every 12dp, one small tile repeated. */
    static Drawable background(Context ctx, int background, int dotColor) {
        float density = ctx.getResources().getDisplayMetrics().density;
        int cell = Math.max(4, Math.round(12 * density));
        Bitmap bmp = Bitmap.createBitmap(cell, cell, Bitmap.Config.ARGB_8888);
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(dotColor);
        new Canvas(bmp).drawCircle(cell / 2f, cell / 2f, 1.1f * density, paint);
        BitmapDrawable dots = new BitmapDrawable(ctx.getResources(), bmp);
        dots.setTileModeXY(Shader.TileMode.REPEAT, Shader.TileMode.REPEAT);
        return new LayerDrawable(new Drawable[]{new ColorDrawable(background), dots});
    }

    /** Colour mode's bullet: a circle in the line colour holding a number or letter in bold. */
    static final class Bullet extends Drawable {
        private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final String label;
        private final int size;

        Bullet(Context ctx, int lineColour, String label, float sizeDp, float textSp) {
            float density = ctx.getResources().getDisplayMetrics().density;
            float scaled = ctx.getResources().getDisplayMetrics().scaledDensity;
            size = Math.round(sizeDp * density);
            this.label = label;
            fill.setColor(lineColour);
            text.setColor(bulletText(lineColour));
            text.setTextSize(textSp * scaled);
            text.setTextAlign(Paint.Align.CENTER);
            text.setTypeface(Typeface.create(ctx.getResources().getFont(R.font.space_mono), Typeface.BOLD));
        }

        @Override
        public void draw(Canvas canvas) {
            float cx = getBounds().exactCenterX(), cy = getBounds().exactCenterY();
            canvas.drawCircle(cx, cy, Math.min(getBounds().width(), getBounds().height()) / 2f, fill);
            Paint.FontMetrics m = text.getFontMetrics();
            canvas.drawText(label, cx, cy - (m.ascent + m.descent) / 2f, text);
        }

        @Override public int getIntrinsicWidth() { return size; }
        @Override public int getIntrinsicHeight() { return size; }
        @Override public void setAlpha(int alpha) { fill.setAlpha(alpha); text.setAlpha(alpha); }
        @Override public void setColorFilter(ColorFilter filter) { fill.setColorFilter(filter); text.setColorFilter(filter); }
        @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    }
}
