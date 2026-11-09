package com.gathin.tvhome;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Shader;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.LayerDrawable;

/** Shared pieces of the dot-matrix design (docs/designs/dot-matrix). */
final class DotMatrix {

    /** Dark mode: background, and the grid's dots in white at 7.5 %. */
    static final int BACKGROUND = 0xFF000000;
    static final int GRID_DOT = 0x13FFFFFF;

    private DotMatrix() {
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
}
