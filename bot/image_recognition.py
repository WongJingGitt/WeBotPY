from os import remove
from typing import Callable
from time import sleep

from agent.image_recognition_agent import ImageRecognitionAgent
from databases.image_recognition_database import ImageRecognitionDatabase
from databases.global_config_database import LLMConfigDatabase
from bot.write_doc import get_all_message, decode_img, DATA_PATH, path
from bot.message import MessageType, TextMessageFromDB
from tool_call.tools import get_msg_handle


class ImageRecognition:
    def __init__(self, model_id, port=19001):
        self._model_id = model_id
        self.port = port

        self._image_recognition_db = ImageRecognitionDatabase()
        self._llm_config_db = LLMConfigDatabase()
        
    def set_model_id(self, model_id):
        self._model_id = model_id

    @property
    def _get_llm_config(self):
        llm_config = self._llm_config_db.get_model_by_id(self._model_id)
        _, _, model_name, base_url, apikey, _, _ = llm_config
        return model_name, base_url, apikey

    @property
    def _image_recognition_agent(self):
        model_name, base_url, apikey = self._get_llm_config
        return ImageRecognitionAgent(model_name=model_name, llm_options={"base_url": base_url, "apikey": apikey}, webot_port=self.port)

    def _get_image_messages(self, start_time, end_time, wxid):
        msg_db_handle = get_msg_handle(self.port)
        all_image_messages = get_all_message(
            wxid=wxid,
            start_time=start_time,
            end_time=end_time,
            port=self.port,
            include_message_type=[MessageType.IMAGE_MESSAGE],
            db_handle=msg_db_handle,
        )
        return all_image_messages

    def run(
            self, wxid, start_time, end_time, 
            on_success: Callable=None, on_error: Callable=None, on_start: Callable=None, on_finally: Callable=None, 
            duration=1, only_failed = False
    ):
        all_image_messages = self._get_image_messages(start_time=start_time, end_time=end_time, wxid=wxid)
        print(f"一共获取到 {len(all_image_messages)} 张图片消息")
        status = 'pending'
        for index, image_message_data in enumerate(all_image_messages):
            print(f"正在处理第 {index + 1} 张图片消息")

            if on_start is not None and isinstance(on_start, Callable):
                on_start(image_message_data)

            image_message = TextMessageFromDB(*image_message_data)
            image_path = decode_img(
                message=image_message,
                save_dir=path.join(DATA_PATH, 'images'),
                port=self.port,
            )
            _, recognition_result, _ = self._image_recognition_db.get_recognition_result(message_id=image_message.MsgSvrID)
            result = ""
            try:
                if not image_path:
                    print(f"第{index + 1} / {len(all_image_messages)}张图片解码失败")
                    if not recognition_result:
                        self._image_recognition_db.add_recognition_result(
                            message_id=image_message.MsgSvrID,
                            recognition_result="无具体描述",
                            message_time=image_message.CreateTime
                        )
                    status = '识别失败, 从微信中下载图片失败。'
                    yield {"total_message": len(all_image_messages), "current_message_index": index + 1, "status": status, "message_id": image_message.MsgSvrID, "recognition_result": None}
                    continue
                
                if only_failed and (recognition_result not in [None, '无具体描述']):
                    print(f"第{index + 1} / {len(all_image_messages)}张图片已识别，跳过")
                    status = '已有识别结果, 跳过'
                    yield {"total_message": len(all_image_messages), "current_message_index": index + 1, "status": status, "message_id": image_message.MsgSvrID, "recognition_result": recognition_result}
                    continue

                [result], [message_id] = self._image_recognition_agent.invoke({
                    "path": image_path,
                    "message_id": image_message.MsgSvrID,
                })
                if not recognition_result:
                    self._image_recognition_db.add_recognition_result(
                        message_id=message_id,
                        recognition_result=result,
                        message_time=image_message.CreateTime
                    )
                else:
                    self._image_recognition_db.update_recognition_result(
                        message_id=message_id,
                        recognition_result=result
                    )
                print(f"处理成功！")
                status = "处理成功！" if result != '无具体描述' else '由于模型API自身原因识别失败'

                if on_success is not None and isinstance(on_success, Callable):
                    on_success(
                        total_message=len(all_image_messages),
                        current_message_index=index + 1,
                        result=result
                    )

            except Exception as e:
                print(f"第{index + 1}张图片识别失败: {e}")
                status = "识别失败！"
                self._image_recognition_db.add_recognition_result(
                    message_id=image_message.MsgSvrID,
                    recognition_result="无具体描述",
                    message_time=image_message.CreateTime
                )
                if on_error is not None and isinstance(on_error, Callable):
                    on_error(e)

            finally:

                # 删除图片会有副作用，导致微信中的图片缓存也丢失
                # try:
                #     dat_path = image_path.replace(".jpg", ".dat")
                #     if path.exists(dat_path):
                #         remove(dat_path)
                #     if path.exists(image_path):
                #         remove(image_path)
                # except Exception as e:
                #     print(f"删除图片失败: {e}")
                if on_finally is not None and isinstance(on_finally, Callable):
                    on_finally(
                        total_message=len(all_image_messages),
                        current_message_index=index + 1,
                        status=status,
                    )
            yield {"total_message": len(all_image_messages), "current_message_index": index + 1, "status": status, "message_id": image_message.MsgSvrID, "recognition_result": result}
            sleep(duration)