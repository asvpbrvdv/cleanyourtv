package com.gathin.tvhome;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

/** The dot-matrix "mode" key (config.xml, a theme's config.json, the Mode segment's on-TV choice). */
public class ModeTest {

    @Test
    public void namesParseInAnyCase() {
        assertEquals(DotMatrix.DARK, DotMatrix.parseMode("dark", DotMatrix.LIGHT));
        assertEquals(DotMatrix.LIGHT, DotMatrix.parseMode(" Light ", DotMatrix.DARK));
        assertEquals(DotMatrix.COLOR, DotMatrix.parseMode("COLOR", DotMatrix.DARK));
        assertEquals(DotMatrix.COLOR, DotMatrix.parseMode("colour", DotMatrix.DARK));
    }

    @Test
    public void anythingElseKeepsTheFallback() {
        assertEquals(DotMatrix.LIGHT, DotMatrix.parseMode(null, DotMatrix.LIGHT));
        assertEquals(DotMatrix.LIGHT, DotMatrix.parseMode("", DotMatrix.LIGHT));
        assertEquals(DotMatrix.DARK, DotMatrix.parseMode("sepia", DotMatrix.DARK));
    }

    @Test
    public void modeSegmentCyclesDarkLightColor() {
        assertEquals(DotMatrix.LIGHT, DotMatrix.next(DotMatrix.DARK));
        assertEquals(DotMatrix.COLOR, DotMatrix.next(DotMatrix.LIGHT));
        assertEquals(DotMatrix.DARK, DotMatrix.next(DotMatrix.COLOR));
        for (int mode : new int[]{DotMatrix.DARK, DotMatrix.LIGHT, DotMatrix.COLOR}) {
            assertEquals(mode, DotMatrix.parseMode(DotMatrix.modeName(mode), -1));
        }
    }
}
