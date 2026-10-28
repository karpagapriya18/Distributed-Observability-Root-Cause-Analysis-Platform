from pathlib import Path
import sys

import pika
from dotenv import dotenv_values


def main():
    env_path = Path(__file__).with_name(".env")

    if not env_path.is_file():
        print("FAIL: .env file not found beside check_rabbitmq.py")
        return 1

    config = dotenv_values(env_path)

    username = config.get("RABBITMQ_DEFAULT_USER")
    password = config.get("RABBITMQ_DEFAULT_PASS")
    virtual_host = config.get("RABBITMQ_DEFAULT_VHOST") or "/"

    if not username or not password:
        print("FAIL: RabbitMQ username or password is missing in .env")
        return 1

    connection = None

    try:
        port = int(config.get("RABBITMQ_PORT") or "25672")

        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host="127.0.0.1",
                port=port,
                virtual_host=virtual_host,
                credentials=pika.PlainCredentials(
                    username,
                    password,
                ),
                connection_attempts=1,
                socket_timeout=10,
                stack_timeout=15,
                blocked_connection_timeout=10,
            )
        )

        print("PASS: Connected to RabbitMQ")

        channel = connection.channel()

        # Create a temporary queue for this test only.
        result = channel.queue_declare(
            queue="",
            exclusive=True,
        )
        queue_name = result.method.queue

        channel.confirm_delivery()

        message = b"Observability test message"

        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=message,
            mandatory=True,
        )

        print("PASS: Message published and confirmed")

        method, properties, body = channel.basic_get(
            queue=queue_name,
            auto_ack=False,
        )

        if method is None:
            print("FAIL: No message received")
            return 1

        if body != message:
            channel.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=False,
            )
            print("FAIL: Received message does not match")
            return 1

        channel.basic_ack(
            delivery_tag=method.delivery_tag,
        )

        print("PASS: Message received and acknowledged")
        print("Result: RabbitMQ messaging test passed!")
        return 0

    except pika.exceptions.ProbableAuthenticationError:
        print("FAIL: RabbitMQ rejected the username or password")
        print("The .env credentials may differ from the broker's saved credentials.")
        return 1

    except pika.exceptions.ProbableAccessDeniedError:
        print("FAIL: Access denied to the configured virtual host")
        print("Check the virtual host and user permissions.")
        return 1

    except pika.exceptions.AMQPConnectionError:
        print("FAIL: Could not establish a RabbitMQ connection")
        print("Check Docker, RabbitMQ status, and RABBITMQ_PORT.")
        return 1

    except Exception as error:
        print(f"FAIL: {type(error).__name__}")
        return 1

    finally:
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except pika.exceptions.AMQPError:
                pass


if __name__ == "__main__":
    sys.exit(main())