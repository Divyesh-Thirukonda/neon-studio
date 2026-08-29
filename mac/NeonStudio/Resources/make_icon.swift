#!/usr/bin/env swift
//
// Generates Resources/AppIcon.icns.
//
// Run once, from this directory:
//     swift make_icon.swift
//
// The result is committed, so an ordinary build needs nothing beyond swiftc.
// The app previously shipped with no icon at all, which meant a blank generic
// placeholder in the Dock, the Finder, and the app switcher.

import AppKit
import Foundation

func drawIcon(size: CGFloat) -> NSImage {
    let image = NSImage(size: NSSize(width: size, height: size))
    image.lockFocus()
    defer { image.unlockFocus() }

    let s = size
    let inset = s * 0.08
    let rect = NSRect(x: inset, y: inset, width: s - inset * 2, height: s - inset * 2)
    let radius = rect.width * 0.225

    // Rounded-square body with a vertical gradient.
    let body = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    NSGradient(
        colors: [
            NSColor(srgbRed: 0.13, green: 0.15, blue: 0.19, alpha: 1),
            NSColor(srgbRed: 0.05, green: 0.06, blue: 0.08, alpha: 1)
        ]
    )?.draw(in: body, angle: -90)

    NSColor(srgbRed: 0.30, green: 0.33, blue: 0.38, alpha: 1).setStroke()
    body.lineWidth = max(1, s * 0.008)
    body.stroke()

    // Waveform bars: the clearest one-glance signal that this is audio software.
    let barCount = 9
    let area = rect.insetBy(dx: rect.width * 0.19, dy: rect.height * 0.26)
    let slot = area.width / CGFloat(barCount)
    let barWidth = slot * 0.52
    let heights: [CGFloat] = [0.30, 0.58, 0.86, 0.46, 1.0, 0.40, 0.78, 0.54, 0.26]
    let colors = [
        NSColor(srgbRed: 0.42, green: 0.78, blue: 0.96, alpha: 1),
        NSColor(srgbRed: 0.36, green: 0.86, blue: 0.60, alpha: 1),
        NSColor(srgbRed: 1.00, green: 0.79, blue: 0.30, alpha: 1),
        NSColor(srgbRed: 1.00, green: 0.52, blue: 0.36, alpha: 1)
    ]

    for index in 0..<barCount {
        let height = max(area.height * heights[index], barWidth)
        let bar = NSRect(
            x: area.minX + CGFloat(index) * slot + (slot - barWidth) / 2,
            y: area.midY - height / 2,
            width: barWidth,
            height: height
        )
        colors[index % colors.count].setFill()
        NSBezierPath(roundedRect: bar, xRadius: barWidth / 2, yRadius: barWidth / 2).fill()
    }

    return image
}

func png(from image: NSImage, pixels: Int) -> Data? {
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: pixels,
        pixelsHigh: pixels,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .calibratedRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else { return nil }
    rep.size = NSSize(width: pixels, height: pixels)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    drawIcon(size: CGFloat(pixels)).draw(in: NSRect(x: 0, y: 0, width: pixels, height: pixels))
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])
}

let here = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let iconset = here.appendingPathComponent("AppIcon.iconset")
try? FileManager.default.removeItem(at: iconset)
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)

let variants: [(name: String, pixels: Int)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32),
    ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256),
    ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024)
]

for variant in variants {
    guard let data = png(from: NSImage(), pixels: variant.pixels) else {
        FileHandle.standardError.write("failed to render \(variant.name)\n".data(using: .utf8)!)
        exit(1)
    }
    try data.write(to: iconset.appendingPathComponent("\(variant.name).png"))
}

let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconset.path, "-o", here.appendingPathComponent("AppIcon.icns").path]
try iconutil.run()
iconutil.waitUntilExit()
try? FileManager.default.removeItem(at: iconset)
print("wrote AppIcon.icns")
