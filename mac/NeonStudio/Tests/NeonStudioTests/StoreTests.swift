import Foundation
import NeonStudioKit

/// Persistence: encoding, decoding, the project library, path resolution, and
/// the subprocess result parser.
enum StoreTests {

    private static func sampleProject(id: String = "demo", name: String = "Demo") -> LocalProject {
        ProjectNormalizer.normalize(LocalProject(
            id: id,
            name: name,
            updatedAt: nowISO(),
            snapshot: ProjectSnapshot(
                bpm: 128,
                tracks: [
                    Track(
                        id: "lead",
                        name: "Lead",
                        kind: "audio",
                        file: "exports/lead.wav",
                        clips: [Clip(id: "c1", name: "Hook", startBar: 0, bars: 8)]
                    )
                ]
            )
        ))
    }

    static func run() {
        let t = TestRunner.shared
        t.section("Encoding and decoding")

        t.test("a project round-trips through encode and decode") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            let original = sampleProject()
            guard let data = try? store.encode(original),
                  let decoded = try? store.decode(data, fallbackName: "demo.neon.json") else {
                return expect(false, "round trip threw")
            }
            expectTrue(decoded == original, "decoded project differed from the original")
        }

        t.test("decode accepts both the bare and the enveloped file shapes") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            let project = sampleProject()

            // Enveloped, which is what the app writes.
            guard let enveloped = try? store.encode(project) else { return expect(false, "encode threw") }
            expectNotNil(try? store.decode(enveloped, fallbackName: "a.neon.json"))

            // Bare LocalProject, which older files and some tools still produce.
            let encoder = JSONEncoder()
            guard let bare = try? encoder.encode(project) else { return expect(false, "bare encode threw") }
            guard let decoded = try? store.decode(bare, fallbackName: "a.neon.json") else {
                return expect(false, "bare decode threw")
            }
            expectEqual(decoded.id, project.id)
        }

        t.test("decode rejects unrelated JSON") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            expectThrows(try store.decode(Data(#"{"hello":"world"}"#.utf8), fallbackName: "x.json"))
        }

        t.section("Unique ids")

        t.test("uniqueProjectId avoids overwriting an existing file") {
            // Regression: import used a HHmmss suffix, so importing the same file
            // twice in one second silently destroyed the first copy.
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            expectEqual(store.uniqueProjectId(basedOn: "song"), "song")

            _ = try? store.saveProject(sampleProject(id: "song", name: "Song"))
            expectEqual(store.uniqueProjectId(basedOn: "song"), "song-2")

            _ = try? store.saveProject(sampleProject(id: "song-2", name: "Song 2"))
            expectEqual(store.uniqueProjectId(basedOn: "song"), "song-3")
        }

        t.test("importing the same file twice keeps both copies") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            let source = temp.url.appendingPathComponent("incoming.neon.json")
            try? store.exportProject(sampleProject(id: "incoming", name: "Incoming"), to: source)

            let first = try? store.importProject(from: source)
            let second = try? store.importProject(from: source)
            expectNotNil(first)
            expectNotNil(second)
            expect(first?.id != second?.id, "two imports collapsed onto one id")
            expectEqual(store.loadProjects().count, 2)
        }

        t.section("Audio path resolution")

        t.test("every historical file-path form resolves") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)

            let absolute = store.audioURL(for: Track(id: "a", name: "A", file: "/tmp/kick.wav"))
            expectEqual(absolute?.path, "/tmp/kick.wav")

            let fileURL = store.audioURL(for: Track(id: "a", name: "A", file: "file:///tmp/snare.wav"))
            expectEqual(fileURL?.path, "/tmp/snare.wav")

            // Legacy web-style paths from when this was served over HTTP.
            let api = store.audioURL(for: Track(id: "a", name: "A", file: "/api/audio/neon_alone_drums.wav"))
            expectEqual(api?.lastPathComponent, "neon_alone_drums.wav")
            expectTrue(api?.path.contains("/exports/") ?? false, "api paths belong in exports/")

            let relative = store.audioURL(for: Track(id: "a", name: "A", file: "exports/lead.wav"))
            expectEqual(relative?.path, temp.url.appendingPathComponent("exports/lead.wav").path)

            expectNil(store.audioURL(for: Track(id: "a", name: "A", file: nil)))
            expectNil(store.audioURL(for: Track(id: "a", name: "A", file: "")))
        }

        t.test("existingAudioURL and audioTrackCounts only count real files") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            temp.write("not really audio, but it exists", to: "exports/real.wav")

            let project = ProjectNormalizer.normalize(LocalProject(
                id: "p",
                name: "P",
                updatedAt: nowISO(),
                snapshot: ProjectSnapshot(bpm: 120, tracks: [
                    Track(id: "a", name: "Has audio", kind: "audio", file: "exports/real.wav"),
                    Track(id: "b", name: "Missing", kind: "audio", file: "exports/missing.wav"),
                    Track(id: "c", name: "No file", kind: "instrument")
                ])
            ))
            expectNotNil(store.existingAudioURL(for: project.snapshot.tracks[0]))
            expectNil(store.existingAudioURL(for: project.snapshot.tracks[1]))
            expectNil(store.existingAudioURL(for: project.snapshot.tracks[2]))

            let counts = store.audioTrackCounts(for: project)
            expectEqual(counts.withAudio, 1)
            expectEqual(counts.total, 3)
        }

        t.section("Project library")

        t.test("factory and stored projects merge, with the stored copy winning") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)

            var factory = sampleProject(id: "shared", name: "Factory Name")
            factory.snapshot.bpm = 100
            let factoryDirectory = temp.subdirectory("factory/projects")
            try? store.exportProject(factory, to: factoryDirectory.appendingPathComponent("shared.neon.json"))
            temp.write(#"{"projects":[{"id":"shared","file":"projects/shared.neon.json"}]}"#,
                       to: "factory/projects/index.json")

            var edited = factory
            edited.name = "My Edit"
            edited.snapshot.bpm = 174
            _ = try? store.saveProject(edited)

            _ = try? store.saveProject(sampleProject(id: "mine", name: "Mine"))

            let projects = store.loadProjects()
            expectEqual(projects.count, 2)
            guard let shared = projects.first(where: { $0.id == "shared" }) else {
                return expect(false, "the shared project vanished")
            }
            expectEqual(shared.name, "My Edit", "the user's edit must win over the bundled copy")
            expectClose(shared.snapshot.bpm, 174)
            expectTrue(store.isFactoryProject("shared"))
            expectFalse(store.isFactoryProject("mine"))
        }

        t.test("deleting a factory project hides it, and it can be restored") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            let factoryDirectory = temp.subdirectory("factory/projects")
            let factory = sampleProject(id: "example", name: "Example")
            try? store.exportProject(factory, to: factoryDirectory.appendingPathComponent("example.neon.json"))
            temp.write(#"{"projects":[{"id":"example","file":"projects/example.neon.json"}]}"#,
                       to: "factory/projects/index.json")

            expectEqual(store.loadProjects().count, 1)
            try? store.deleteProject(factory)
            expectEqual(store.loadProjects().count, 0)
            expectEqual(store.hiddenFactoryProjectCount, 1)

            try? store.restoreDeletedFactoryProjects()
            expectEqual(store.loadProjects().count, 1)
            expectEqual(store.hiddenFactoryProjectCount, 0)
        }

        t.test("two files claiming the same id do not crash the library") {
            // Regression: this used Dictionary(uniqueKeysWithValues:), which
            // traps on a duplicate key and took the whole app down at launch.
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            let directory = temp.subdirectory("data/projects")
            var a = sampleProject(id: "clash", name: "A")
            a.snapshot.bpm = 100
            var b = sampleProject(id: "clash", name: "B")
            b.snapshot.bpm = 140
            try? store.exportProject(a, to: directory.appendingPathComponent("clash.neon.json"))
            try? store.exportProject(b, to: directory.appendingPathComponent("clash-copy.neon.json"))
            expectEqual(store.loadProjects().count, 2, "both files should be listed, not trap")
        }

        t.test("projects are ordered by their real modification date") {
            let temp = TempDirectory(); defer { temp.cleanUp() }
            let store = ProjectStore(rootURL: temp.url)
            var older = sampleProject(id: "older", name: "Older")
            older.updatedAt = "2026-01-01T00:00:00Z"
            var newer = sampleProject(id: "newer", name: "Newer")
            // Fractional seconds used to sort *before* whole ones as raw strings.
            newer.updatedAt = "2026-06-01T00:00:00.500Z"
            _ = try? store.saveProject(older)
            _ = try? store.saveProject(newer)
            expectEqual(store.loadProjects().first?.id, "newer")
        }

        t.section("Tool output parsing")

        t.test("the last JSON object is found past trailing progress lines") {
            let result = ToolResult(
                standardOutput: """
                Loading project…
                {"progress": 1}
                {"verdict": {"score": 86}, "strengths": ["wide"]}

                done
                """,
                standardError: "",
                exitCode: 0
            )
            let json = result.lastJSONObject
            expectNotNil(json["verdict"])
            expectNil(json["progress"])
            expectTrue(result.succeeded)
        }

        t.test("output with no JSON gives an empty dictionary rather than crashing") {
            let result = ToolResult(standardOutput: "nothing structured here\n", standardError: "", exitCode: 0)
            expectTrue(result.lastJSONObject.isEmpty)
        }

        t.test("a non-zero exit code is not a success") {
            let result = ToolResult(standardOutput: "", standardError: "boom", exitCode: 2)
            expectFalse(result.succeeded)
        }
    }
}
