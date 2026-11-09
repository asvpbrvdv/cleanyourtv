package com.gathin.tvhome;

import android.animation.ValueAnimator;
import android.graphics.ColorMatrix;
import android.graphics.ColorMatrixColorFilter;
import android.widget.ImageView;

/**
 * Dot-matrix tiles: unfocused banners in greyscale, the focused one in full colour. {@code amount} runs from 0
 * (grey, at the mode's brightness and contrast: dark ×0.75, light contrast 0.92) to 1 (the banner's own
 * colours, no filter at all).
 */
final class TileTint {

    private TileTint() {
    }

    /** The filter for this amount of colour, or null at full colour (drawn with no filter). */
    static ColorMatrixColorFilter filter(DotMatrix.Palette p, float amount) {
        if (amount >= 1f) return null;
        ColorMatrix m = new ColorMatrix();
        m.setSaturation(amount);
        float b = p.greyBrightness + (1f - p.greyBrightness) * amount;
        float c = p.greyContrast + (1f - p.greyContrast) * amount;
        // Contrast c around mid-grey, then brightness b.
        float t = 128f * (1f - c) * b;
        m.postConcat(new ColorMatrix(new float[]{
                c * b, 0, 0, 0, t,
                0, c * b, 0, 0, t,
                0, 0, c * b, 0, t,
                0, 0, 0, 1, 0}));
        return new ColorMatrixColorFilter(m);
    }

    static void set(DotMatrix.Palette p, float amount, ImageView... views) {
        ColorMatrixColorFilter f = filter(p, amount);
        for (ImageView v : views) v.setColorFilter(f);
    }

    /** Fades the tile's artwork between grey and colour; returns the animator so a new focus change can cancel it. */
    static ValueAnimator animate(DotMatrix.Palette p, boolean toColour, long ms, ImageView... views) {
        ValueAnimator a = ValueAnimator.ofFloat(toColour ? 0f : 1f, toColour ? 1f : 0f);
        a.setDuration(ms);
        a.addUpdateListener(an -> set(p, (float) an.getAnimatedValue(), views));
        a.start();
        return a;
    }
}
