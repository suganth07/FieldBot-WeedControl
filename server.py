import RPi.GPIO as GPIO
from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
import time
import math
import uvicorn

# Initialize FastAPI app
app = FastAPI(title="Robot Control API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define GPIO pins
# Motor control pins
PWM1, DIR1 = 18, 23  # Motor 1 (Left)
PWM2, DIR2 = 19, 24  # Motor 2 (Right)
# Camera servo pin
SERVO_PIN = 17
# Spray control pins
RELAY_PIN = 26       # Spray motor relay
SPRAY_SERVO_PIN = 27 # Spray nozzle servo

# Robot parameters
WHEEL_DIAMETER = 0.15  # 15cm in meters
MAX_RPM = 50
SERVO_ANGLES = {
    "left": 60,
    "right": 120,
    "straight": 90
}

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup([PWM1, DIR1, PWM2, DIR2, SERVO_PIN, RELAY_PIN, SPRAY_SERVO_PIN], GPIO.OUT)

# Initialize all outputs to safe states
GPIO.output(RELAY_PIN, GPIO.HIGH)  # Relay OFF initially
GPIO.output([PWM1, PWM2, DIR1, DIR2], GPIO.LOW)

# Setup PWMs
pwm1 = GPIO.PWM(PWM1, 1000)
pwm2 = GPIO.PWM(PWM2, 1000)
camera_servo_pwm = GPIO.PWM(SERVO_PIN, 50)  # Camera servo needs 50Hz
spray_servo_pwm = GPIO.PWM(SPRAY_SERVO_PIN, 50)  # Spray servo needs 50Hz

# Start PWMs
pwm1.start(0)
pwm2.start(0)
camera_servo_pwm.start(0)
spray_servo_pwm.start(0)

# Define request models
class MotorParams(BaseModel):
    distance: float = Field(..., description="Distance to move in meters")
    speed: int = Field(10, description="Motor speed (0-100)", ge=0, le=100)

class CameraDirection(BaseModel):
    direction: str = Field(..., description="Camera direction (left/right/straight)")

class SprayAngle(BaseModel):
    angle: float = Field(..., ge=0, le=180, description="Spray direction angle (0-180 degrees)")

# Movement function
def move_motor(direction: str, distance: float, speed: int):
    """Controls the motor movement in a given direction for a specific distance and speed."""
    try:
        if direction == "forward":
            GPIO.output(DIR1, GPIO.LOW)
            GPIO.output(DIR2, GPIO.LOW)
        elif direction == "backward":
            GPIO.output(DIR1, GPIO.HIGH)
            GPIO.output(DIR2, GPIO.HIGH)
        elif direction == "left":
            GPIO.output(DIR1, GPIO.HIGH)
            GPIO.output(DIR2, GPIO.LOW)
            speed = speed // 2  # Reduce speed for turning
        elif direction == "right":
            GPIO.output(DIR1, GPIO.LOW)
            GPIO.output(DIR2, GPIO.HIGH)
            speed = speed // 2  # Reduce speed for turning
        else:
            return "Invalid direction"

        pwm1.ChangeDutyCycle(speed)
        pwm2.ChangeDutyCycle(speed)

        # Calculate movement time based on distance and speed
        if speed <= 0:
            time_needed = 0
        else:
            circumference = math.pi * WHEEL_DIAMETER
            rpm = MAX_RPM * (speed / 100)
            rps = rpm / 60  # Convert RPM to revolutions per second
            linear_speed = circumference * rps  # meters per second
            time_needed = distance / linear_speed

        time.sleep(time_needed)

        pwm1.ChangeDutyCycle(0)
        pwm2.ChangeDutyCycle(0)

        return f"Moved {direction} for {distance} meters at {speed}% speed"
    except Exception as e:
        return f"Error: {str(e)}"

# Camera control function
def rotate_camera(direction: str):
    """Rotate camera servo to specified direction"""
    try:
        angle = SERVO_ANGLES.get(direction.lower())
        if angle is None:
            return f"Invalid direction: {direction}. Use 'left', 'right', or 'straight'."

        duty = 2.5 + (angle / 18)
        camera_servo_pwm.ChangeDutyCycle(duty)
        time.sleep(0.5)
        camera_servo_pwm.ChangeDutyCycle(0)  # Stop signal to prevent jitter
        return f"Camera rotated {direction} ({angle}°)"
    except Exception as e:
        return f"Camera error: {str(e)}"

# Spray control functions
def adjust_spray_angle(angle: float):
    """Control spray nozzle direction"""
    try:
        duty = 2.5 + (angle / 18)
        spray_servo_pwm.ChangeDutyCycle(duty)
        time.sleep(0.5)
        spray_servo_pwm.ChangeDutyCycle(0)  # Stop signal to prevent jitter
        return f"Spray nozzle rotated to {angle}°"
    except Exception as e:
        return f"Spray angle error: {str(e)}"

def activate_spray(duration: float = 5.0):
    """Activate spray mechanism for specified duration"""
    try:
        GPIO.output(RELAY_PIN, GPIO.LOW)  # Relay ON
        time.sleep(duration)
        GPIO.output(RELAY_PIN, GPIO.HIGH)  # Relay OFF
        return f"Spray activated for {duration} seconds"
    except Exception as e:
        return f"Spray activation error: {str(e)}"

# Motor control endpoints
@app.post("/forward")
async def move_forward(params: MotorParams):
    """Move the robot forward"""
    return {"status": move_motor("forward", params.distance, params.speed)}

@app.post("/backward")
async def move_backward(params: MotorParams):
    """Move the robot backward"""
    return {"status": move_motor("backward", params.distance, params.speed)}

@app.post("/left")
async def turn_left(params: MotorParams):
    """Turn the robot left"""
    return {"status": move_motor("left", params.distance, params.speed)}

@app.post("/right")
async def turn_right(params: MotorParams):
    """Turn the robot right"""
    return {"status": move_motor("right", params.distance, params.speed)}

@app.post("/stop")
async def stop_motor():
    """Stop the robot's motors"""
    pwm1.ChangeDutyCycle(0)
    pwm2.ChangeDutyCycle(0)
    return {"status": "Motor stopped"}

# Camera control endpoint
@app.post("/camera/{direction}")
async def control_camera(direction: str):
    """Control camera direction (left/right/straight)"""
    return {"status": rotate_camera(direction)}

# Spray control endpoints
@app.post("/turn_spray")
async def set_spray_angle(angle: SprayAngle):
    """Adjust spray nozzle angle"""
    return {"status": adjust_spray_angle(angle.angle)}

@app.post("/activate_spray")
async def spray_activate(duration: float = 5.0):
    """Activate spray mechanism"""
    return {"status": activate_spray(duration)}

@app.on_event("shutdown")
def cleanup():
    """Cleanup GPIO on shutdown"""
    pwm1.stop()
    pwm2.stop()
    camera_servo_pwm.stop()
    spray_servo_pwm.stop()
    GPIO.output(RELAY_PIN, GPIO.HIGH)  # Ensure spray is off
    GPIO.cleanup()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)