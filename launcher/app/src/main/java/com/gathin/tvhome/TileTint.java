package com.gathin.tvhome;

import android.animation.ValueAnimator;
import android.graphics.ColorMatrix;
import android.graphics.ColorMatrixColorFilter;
import android.widget.ImageView;

/**
 * Dot-matrix tiles: unfocused banners in greyscale, the focused one in full colour. {@code amount} runs from 0
 * (grey, at {@link #GREY_BRIGHTNESS}) to 1 (the banner's own colours, no filter at all).
 */
final class TileTint {

    /** Dark mode: grey tiles at three quarters of their brightness, so the focused one stands out. */
    static final float GREY_BRIGHTNESS = 0.75f;

    private TileTint() {
    }

    /** The filter for this amount of colour, or null at full colour (drawn with no filter). */
    static ColorMatrixColorFilter filter(float amount) {
        if (amount >= 1f) return null;
        ColorMatrix m = new ColorMatrix();
        m.setSaturation(amount);
        float b = GREY_BRIGHTNESS + (1f - GREY_BRIGHTNESS) * amount;
        ColorMatrix scale = new ColorMatrix();
        scale.setScale(b, b, b, 1f);
        m.postConcat(scale);
        return new ColorMatrixColorFilter(m);
    }

    static void set(float amount, ImageView... views) {
        ColorMatrixColorFilter f = filter(amount);
        for (ImageView v : views) v.setColorFilter(f);
    }

    /** Fades the tile's artwork between grey and colour; returns the animator so a new focus change can cancel it. */
    static ValueAnimator animate(boolean toColour, long ms, ImageView... views) {
        ValueAnimator a = ValueAnimator.ofFloat(toColour ? 0f : 1f, toColour ? 1f : 0f);
        a.setDuration(ms);
        a.addUpdateListener(an -> set((float) an.getAnimatedValue(), views));
        a.start();
        return a;
    }
}
