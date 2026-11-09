package com.gathin.tvhome;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.View;

/**
 * The focus ring of the dot-matrix design: a 2dp ring in the ink colour just outside the zoomed tile. One
 * instance floats over the grid and is moved with spring animations between tiles. (It was a glass slab, hence
 * the name.)
 */
public class GlassView extends View {

    /** Space between the view's edge and the zoomed tile, as MainActivity sizes it (tile plus this on each side). */
    static final float INSET_DP = 6f;

    private final Paint ring = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final float density;
    private float radius;
    /** The ring's colour when no accent is set: the mode's ink. */
    private int ink = 0xFFF2F2F2;
    private int accent;

    public GlassView(Context context, AttributeSet attrs) {
        super(context, attrs);
        density = getResources().getDisplayMetrics().density;
        radius = 14f * density;
        ring.setStyle(Paint.Style.STROKE);
        ring.setStrokeWidth(2f * density);
        ring.setColor(ink);
        // Cache the ring as a texture. The spring only changes translation, so the GPU can move it without
        // drawing it again on every frame.
        setLayerType(LAYER_TYPE_HARDWARE, null);
    }

    /** Colours the ring (a festival, reorder mode, colour mode); 0 restores the ink colour. */
    void setAccent(int argb) {
        accent = argb;
        ring.setColor(argb == 0 ? ink : 0xFF000000 | argb);
        invalidate();
    }

    /** The mode's ink colour, used while no accent is set. */
    void setInk(int argb) {
        ink = argb;
        if (accent == 0) ring.setColor(argb);
        invalidate();
    }

    /** Corner radius of the zoomed tile; the ring follows it 1dp further out. */
    void setRadius(float px) {
        radius = px;
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        // The stroke is centred on this rect: it covers the 2dp just outside the tile.
        float o = INSET_DP * density - density;
        rect.set(o, o, getWidth() - o, getHeight() - o);
        canvas.drawRoundRect(rect, radius + density, radius + density, ring);
    }
}
