import React, {Component} from 'react';
import io from 'socket.io-client';

const DOWNSAMPLING_WORKER = '/static/build/downsampling_worker.js';

class App extends Component {
	constructor(props) {
		super(props);
		this.state = {
			connected: false,
			recording: false,
			recordingStart: 0,
			recordingTime: 0,
			recognitionCount: 0,
			recognitionOutput: [],
			modelName: props.modelName
		};
	}

	componentDidMount() {
		this.socket = io();

		this.socket.emit('start', this.props.modelName);

		this.socket.on('connect', () => {
			console.log('socket connected');
			this.setState({connected: true});
		});

		this.socket.on('disconnect', () => {
			console.log('socket disconnected');
			this.setState({connected: false});
			this.stopRecording();
		});

		this.socket.on('recognize', (results) => {
			console.log('recognized:', results);
			let {recognitionCount, recognitionOutput} = this.state;
			recognitionOutput[0].text = results.text;
			recognitionOutput.unshift({id: recognitionCount++, text: ""});
			// Keep only 5 results visible
			recognitionOutput = recognitionOutput.slice(0, 5);
			this.setState({recognitionCount, recognitionOutput});
		});

		this.socket.on('intermediate', (results) => {
			console.log('intermediate:', results);
			let {recognitionOutput} = this.state;
			recognitionOutput[0].text = results.text;
			this.setState({recognitionOutput});
		});
	}

	render() {
		return (<div className="App">
			<div>
				<button class="rec-btn btn btn-outline-dark" disabled={!this.state.connected || this.state.recording} onClick={this.startRecording}>
					Start Recording
				</button>

				<button class="rec-btn btn btn-outline-dark" disabled={!this.state.recording} onClick={this.stopRecording}>
					Stop Recording
				</button>

				{this.renderTime()}
			</div>
			{this.renderRecognitionOutput()}
		</div>);
	}

	renderTime() {
		return (<span class="time-badge badge bg-secondary">
			{(Math.round(this.state.recordingTime / 100) / 10).toFixed(1)}s
		</span>);
	}

	renderRecognitionOutput() {
		return (<ul class="stt-results-list">
			{this.state.recognitionOutput.map((r) => {
				return (<li key={r.id}>{r.text}</li>);
			})}
		</ul>)
	}

	createAudioProcessor(audioContext, audioSource) {
		let processor = audioContext.createScriptProcessor(4096, 1, 1);

		const sampleRate = audioSource.context.sampleRate;

		let downsampler = new Worker(DOWNSAMPLING_WORKER);
		downsampler.postMessage({command: "init", inputSampleRate: sampleRate});
		downsampler.onmessage = (e) => {
			if (this.socket.connected) {
				this.socket.emit('stream-data', e.data.buffer);
			}
		};

		processor.onaudioprocess = (event) => {
			var data = event.inputBuffer.getChannelData(0);
			downsampler.postMessage({command: "process", inputFrame: data});
		};

		processor.shutdown = () => {
			processor.disconnect();
			this.onaudioprocess = null;
		};

		processor.connect(audioContext.destination);

		return processor;
	}

	startRecording = e => {
		if (!this.state.recording) {
			let {recognitionCount, recognitionOutput} = this.state;
			recognitionOutput.unshift({id: recognitionCount++, text: ""});
			this.setState({recognitionCount, recognitionOutput});

			this.recordingInterval = setInterval(() => {
				let recordingTime = new Date().getTime() - this.state.recordingStart;
				this.setState({recordingTime});
			}, 100);

			this.updatesInterval = setInterval(() => {
				this.socket.emit("stream-intermediate");
			}, 400);

			this.setState({
				recording: true,
				recordingStart: new Date().getTime(),
				recordingTime: 0
			}, () => {
				this.startMicrophone();
			});
		}
	};

	startMicrophone() {
		this.audioContext = new AudioContext();

		const success = (stream) => {
			console.log('started recording');
			this.mediaStream = stream;
			this.mediaStreamSource = this.audioContext.createMediaStreamSource(stream);
			this.processor = this.createAudioProcessor(this.audioContext, this.mediaStreamSource);
			this.mediaStreamSource.connect(this.processor);
		};

		const fail = (e) => {
			console.error('recording failure', e);
		};

		if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
			navigator.mediaDevices.getUserMedia({
				video: false,
				audio: true
			})
			.then(success)
			.catch(fail);
		}
		else {
			navigator.getUserMedia({
				video: false,
				audio: true
			}, success, fail);
		}
	}

	stopRecording = e => {
		if (this.state.recording) {
			let {recognitionCount, recognitionOutput} = this.state;
			if (recognitionOutput[0].text.length === 0) {
				recognitionOutput = recognitionOutput.slice(1);
				recognitionCount--;
				this.setState({recognitionCount, recognitionOutput});
			}

			if (this.socket.connected) {
				this.socket.emit('stream-reset');
			}
			clearInterval(this.recordingInterval);
			clearInterval(this.updatesInterval);
			this.setState({
				recording: false
			}, () => {
				this.stopMicrophone();
			});
		}
	};

	stopMicrophone() {
		if (this.mediaStream) {
			this.mediaStream.getTracks()[0].stop();
		}
		if (this.mediaStreamSource) {
			this.mediaStreamSource.disconnect();
		}
		if (this.processor) {
			this.processor.shutdown();
		}
		if (this.audioContext) {
			this.audioContext.close();
		}
	}
}

export default App;
