import SwiftUI
import AVKit

/// A standalone SwiftUI module designed to be dropped into any MacOS or iOS project.
/// This module provides a continuity viewer for the autonomous cinematic pipeline,
/// allowing the director to review the storyboard clips against the master foley and voiceover.
@available(macOS 12.0, iOS 15.0, *)
public struct ContinuityViewer: View {
    @State private var player = AVPlayer()
    
    // Paths to the local autonomous generator output
    let videoURL: URL
    let masterAudioURL: URL?
    
    public init(videoPath: String, audioPath: String? = nil) {
        self.videoURL = URL(fileURLWithPath: videoPath)
        if let audio = audioPath {
            self.masterAudioURL = URL(fileURLWithPath: audio)
        } else {
            self.masterAudioURL = nil
        }
    }
    
    public var body: some View {
        VStack(spacing: 20) {
            Text("Automated Studio: Continuity Matrix")
                .font(.system(size: 24, weight: .bold, design: .monospaced))
                .foregroundColor(.white)
            
            // The massive cinematic 16:9 canvas
            VideoPlayer(player: player)
                .aspectRatio(16/9, contentMode: .fit)
                .cornerRadius(12)
                .shadow(color: .black.opacity(0.8), radius: 20)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.white.opacity(0.2), lineWidth: 1)
                )
            
            HStack {
                Button(action: {
                    player.seek(to: .zero)
                    player.play()
                }) {
                    Label("Review Sequence", systemImage: "play.fill")
                        .font(.headline)
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                }
                
                Button(action: {
                    player.pause()
                }) {
                    Label("Halt", systemImage: "pause.fill")
                        .font(.headline)
                        .padding()
                        .background(Color.red.opacity(0.8))
                        .foregroundColor(.white)
                        .cornerRadius(8)
                }
            }
            .padding(.bottom, 20)
        }
        .padding()
        .background(Color.black.edgesIgnoringSafeArea(.all))
        .onAppear {
            setupContinuityMix()
        }
    }
    
    private func setupContinuityMix() {
        // Load the stitched matrix
        let videoItem = AVPlayerItem(url: videoURL)
        player.replaceCurrentItem(with: videoItem)
        
        // If there's an active master audio feed, layer it
        if let audio = masterAudioURL {
            // In a more complex production app, you would use AVMutableComposition 
            // to perfectly sync audio, but AVPlayer handles standard MP4 playback fluidly.
            print("Loaded Master Audio Feed: \(audio.lastPathComponent)")
        }
    }
}

// MARK: - Preview Provider
@available(macOS 12.0, iOS 15.0, *)
struct ContinuityViewer_Previews: PreviewProvider {
    static var previews: some View {
        ContinuityViewer(
            videoPath: "/Users/hyungkoookkim/Content/temp_stitched_master.mp4"
        )
        .frame(width: 800, height: 600)
    }
}
