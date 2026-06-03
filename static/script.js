// write a script to fetch chat data from the server and display it in the chat window
fetch('/chat/<session_id>', {
 method: "POST",
 headers: {
   "Content-Type": "application/json"
 },
 body: JSON.stringify({
})}).then(response => response.json())
.then(data => {
  const chatWindow = document.getElementById('chat-window');
  data.forEach(message => {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message');
    messageElement.innerText = `${message.sender}: ${message.text}`;
    chatWindow.appendChild(messageElement);
  });
})

