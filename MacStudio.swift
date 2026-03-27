import SwiftUI
import AVKit
import Foundation
import AppKit

struct AVPlayerViewRepresentable: NSViewRepresentable {
    let player: AVPlayer
    func makeNSView(context: Context) -> AVPlayerView {
        let view = AVPlayerView()
        view.player = player
        view.controlsStyle = .inline
        return view
    }
    func updateNSView(_ nsView: AVPlayerView, context: Context) {
        nsView.player = player
    }
}

@main
struct MacStudioApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    var body: some Scene {
        WindowGroup {
            StudioDashboardView()
                .frame(minWidth: 900, idealWidth: 1200, minHeight: 600, idealHeight: 800)
        }
        .windowStyle(HiddenTitleBarWindowStyle())
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

struct FilmProject: Identifiable, Hashable {
    let id = UUID()
    let title: String
    let videoPath: URL
}

struct StudioDashboardView: View {
    @State private var projects: [FilmProject] = []
    @State private var selectedProject: FilmProject?
    @State private var isGenerating = false
    @State private var pipelineLogs = "System standing by...\n"
    
    // The path to the Python workspace
    let workspaceRoot = "/Users/hyungkoookkim/Content"
    
    var body: some View {
        NavigationView {
            // LEFT SIDEBAR: Controls & Library
            VStack(alignment: .leading, spacing: 10) {
                Text("A24 Engine Core")
                    .font(.system(size: 20, weight: .heavy, design: .monospaced))
                    .padding(.top, 20)
                    .padding(.horizontal)
                
                Button(action: {
                    runPythonPipeline()
                }) {
                    HStack {
                        Image(systemName: isGenerating ? "gearshape.2.fill" : "bolt.fill")
                        Text(isGenerating ? "Synthesizing Film..." : "Generate Masterpiece")
                            .font(.headline)
                    }
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(isGenerating ? Color.orange : Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(10)
                    .shadow(radius: 5)
                }
                .disabled(isGenerating)
                .padding(.horizontal)
                .padding(.bottom, 15)
                
                Text("SYSTEM LOGS")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundColor(.gray)
                    .padding(.horizontal)
                
                ScrollView {
                    Text(pipelineLogs)
                        .font(.custom("Menlo", size: 10))
                        .foregroundColor(.green)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .frame(height: 100)
                .background(Color.black)
                .cornerRadius(8)
                .padding(.horizontal)
                
                Text("ARCHIVES")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundColor(.gray)
                    .padding(.horizontal)
                    .padding(.top, 10)
                
                List(projects, selection: $selectedProject) { project in
                    NavigationLink(destination: ContinuityViewer(videoURL: project.videoPath, title: project.title)) {
                        VStack(alignment: .leading) {
                            Text(project.title)
                                .font(.subheadline)
                                .fontWeight(.medium)
                            Text("16:9 Widescreen Master")
                                .font(.caption2)
                                .foregroundColor(.gray)
                        }
                        .padding(.vertical, 4)
                    }
                    .tag(project)
                }
                .listStyle(SidebarListStyle())
            }
            .frame(minWidth: 280, idealWidth: 320, maxWidth: 350)
            
            // RIGHT MAIN PANEL: Placeholder
            VStack {
                Image(systemName: "film")
                    .font(.system(size: 60))
                    .foregroundColor(.gray.opacity(0.3))
                Text("Select a film from the archives to review continuity.")
                    .font(.headline)
                    .foregroundColor(.gray)
                    .padding(.top, 10)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(NSColor.windowBackgroundColor))
        }
        .onAppear(perform: loadProjects)
    }
    
    /// Scans the export directory for generated MP4 sequences
    func loadProjects() {
        let fileManager = FileManager.default
        let exportsURL = URL(fileURLWithPath: "\(workspaceRoot)/exports")
        
        var loadedProjects: [FilmProject] = []
        
        if let enumerator = fileManager.enumerator(at: exportsURL, includingPropertiesForKeys: [.isDirectoryKey]) {
            for case let fileURL as URL in enumerator {
                if fileURL.pathExtension == "mp4" {
                    // Extract the folder name as the project title
                    let folderName = fileURL.deletingLastPathComponent().lastPathComponent
                    // Clean up folder name aesthetically
                    let cleanTitle = folderName.replacingOccurrences(of: "_", with: " ").capitalized
                    
                    loadedProjects.append(FilmProject(title: cleanTitle, videoPath: fileURL))
                }
            }
        }
        
        self.projects = loadedProjects.sorted { $0.title < $1.title }
    }
    
    /// Spawns a background process to construct the film
    func runPythonPipeline() {
        isGenerating = true
        self.pipelineLogs = "Initializing autonomous pipeline..."
        
        DispatchQueue.global(qos: .userInitiated).async {
            let task = Process()
            task.executableURL = URL(fileURLWithPath: "/bin/bash")
            let cmd = "cd \(self.workspaceRoot) && ./.venv/bin/python main.py"
            task.arguments = ["-c", cmd]
            
            // Capture output
            let pipe = Pipe()
            task.standardOutput = pipe
            task.standardError = pipe
            
            do {
                try task.run()
                
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let outputLog = String(data: data, encoding: .utf8) ?? "No output."
                
                task.waitUntilExit()
                
                DispatchQueue.main.async {
                    self.pipelineLogs = "Pipeline Execution Finished.\nSee terminal or exports folder.\nLog Snapshot:\n\(String(outputLog.prefix(400)))"
                    self.isGenerating = false
                    self.loadProjects() // Refresh
                }
            } catch {
                DispatchQueue.main.async {
                    self.pipelineLogs = "Failed to launch pipeline: \(error.localizedDescription)"
                    self.isGenerating = false
                }
            }
        }
    }
}

/// The Cinematic 16:9 Monitor
struct ContinuityViewer: View {
    @State private var player = AVPlayer()
    
    let videoURL: URL
    let title: String
    
    var body: some View {
        VStack(spacing: 20) {
            Text(title)
                .font(.system(size: 28, weight: .bold, design: .serif))
                .foregroundColor(.white)
                .padding(.top, 30)
            
            // The massive cinematic 16:9 canvas
            AVPlayerViewRepresentable(player: player)
                .aspectRatio(16/9, contentMode: .fit)
                .cornerRadius(12)
                .shadow(color: .black.opacity(0.8), radius: 30)
                .padding(.horizontal, 40)
            
            HStack(spacing: 40) {
                Button(action: {
                    player.seek(to: .zero)
                    player.play()
                }) {
                    Label("PLAY SEQUENCE", systemImage: "play.fill")
                        .font(.headline)
                        .padding()
                        .frame(width: 180)
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                }
                .buttonStyle(PlainButtonStyle())
                
                Button(action: {
                    player.pause()
                }) {
                    Label("PAUSE", systemImage: "pause.fill")
                        .font(.headline)
                        .padding()
                        .frame(width: 140)
                        .background(Color.gray.opacity(0.5))
                        .foregroundColor(.white)
                        .cornerRadius(8)
                }
                .buttonStyle(PlainButtonStyle())
            }
            .padding(.bottom, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.edgesIgnoringSafeArea(.all))
        .onAppear {
            let videoItem = AVPlayerItem(url: videoURL)
            player.replaceCurrentItem(with: videoItem)
        }
        .onDisappear {
            player.pause()
        }
    }
}
